"""The expectations catalogue itself — spec 02 §8 and ADR-0013.

"A rule recorded only in a document drifts; enforced, it is both a guardrail for
the coding agent and a judging artifact." These tests check that the enforced set
is complete and that the two regex-driven expectations agree with the Python
predicates ``transformations.py`` uses, since a rule enforced twice in ways that
disagree is worse than a rule enforced once.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

import pytest

import expectations as X
import transformations as T

CATALOGUE = X.all_expectations(_dt.date(2025, 6, 30), k=20)
PIPELINE_SOURCE = (Path(__file__).resolve().parent.parent / "dlt_pipeline.py").read_text()


def _sql_regex_to_python(pattern: str) -> str:
    """Undo the Spark SQL string-literal escaping so the regex can be compiled.

    Spark processes backslash escapes inside ``'...'``, so ``\\b`` in the Python
    source reaches RLIKE as ``\\b`` the regex word boundary.
    """
    return pattern.replace("\\\\", "\\")


# --- Completeness ----------------------------------------------------------

def test_every_dataset_has_a_catalogue():
    assert set(CATALOGUE) == set(T.SCHEMAS) | {
        "qa_severity_agreement", "qa_pattern_consistency", "qa_similarity_rank_density"
    }


def test_all_twenty_numbered_expectations_are_enforced_somewhere():
    numbered = set()
    for rules in CATALOGUE.values():
        for name in rules:
            match = re.match(r"^E(\d+)_", name)
            if match:
                numbered.add(int(match.group(1)))
    assert numbered == set(range(1, 21)), sorted(set(range(1, 21)) - numbered)


def test_e20_is_documented_as_a_schema_review_not_a_row_predicate():
    """Spec 02 §8 enforces E20 by review against the specification, since it is
    a property of the schema rather than of a row."""
    assert "E20" in PIPELINE_SOURCE
    assert "property of the schema" in PIPELINE_SOURCE
    assert "not of a row" in PIPELINE_SOURCE
    # And the review names the columns it cleared.
    for column in ("last_material_change_date", "last_claim_date",
                   "material_changes_per_year", "term_end_date"):
        assert column in PIPELINE_SOURCE, column


def test_expectations_fail_the_run_rather_than_quarantining_rows():
    """ADR-0013: these rules are the product's correctness, not a quality score."""
    assert "expect_all_or_fail" in PIPELINE_SOURCE
    assert "expect_all_or_drop" not in PIPELINE_SOURCE
    decorators = re.findall(r"^@dlt\.expect_all_or_fail", PIPELINE_SOURCE, re.M)
    # Six curated tables plus the three cross-table assertion tables.
    assert len(decorators) == 9


def test_every_curated_table_has_expectations_attached():
    for table in T.SCHEMAS:
        assert CATALOGUE[table], table


# --- Well-formedness -------------------------------------------------------

@pytest.mark.parametrize("dataset", sorted(CATALOGUE))
def test_expectation_strings_are_well_formed(dataset):
    for name, sql in CATALOGUE[dataset].items():
        assert sql.strip(), name
        assert sql.count("(") == sql.count(")"), f"{name}: unbalanced parentheses"
        assert sql.count("'") % 2 == 0, f"{name}: unbalanced quotes"
        assert not name[0].isdigit()


def test_expectation_names_are_unique_within_a_dataset():
    for dataset, rules in CATALOGUE.items():
        assert len(rules) == len(set(rules)), dataset


def test_rank_is_backtick_quoted_because_it_is_a_reserved_word():
    assert "`rank`" in CATALOGUE["policy_similarity"][
        "E16_rank_is_within_the_documented_cap"]


def test_anchor_date_is_interpolated_as_a_date_literal():
    sql = CATALOGUE["policy_change_event"]["E17_change_date_does_not_exceed_the_anchor"]
    assert "DATE'2025-06-30'" in sql


# --- E19: the SQL guard and the Python predicate must agree ---------------

def test_e19_sql_regex_matches_the_python_policy_id_pattern():
    compiled = re.compile(_sql_regex_to_python(X.POLICY_ID_RLIKE))
    for value in ("P-18492", "p-18492", "policy P-00001 here"):
        assert compiled.search(value), value
        assert T.matches_policy_id_pattern(value)
    for value in ("CLM-002317", "CHG-00931744", "END-00418302", "P-1849", "TLE-N-18492"):
        assert not compiled.search(value), value
        assert not T.matches_policy_id_pattern(value)


def test_e19_regex_is_the_pattern_the_app_uses():
    """ADR-0007: the app detects policy references with this exact pattern, so a
    drift here silently breaks timeline routing."""
    assert _sql_regex_to_python(X.POLICY_ID_RLIKE) == r"(?i)\bP-[0-9]{5}\b"
    assert T.POLICY_ID_PATTERN.pattern == r"\bP-\d{5}\b"


# --- E18: the SQL guard and the Python predicate must agree ---------------

@pytest.mark.parametrize("phrase", [
    "possible fraud", "a fraudulent claim", "a suspicious change",
    "part of a scheme", "deceptive", "guilty", "raises the risk score",
    "this predicts a claim", "causes claims", "leads to a claim",
    "increases the risk of a claim", "an anomaly", "a red flag",
])
def test_e18_sql_regex_catches_every_banned_term(phrase):
    compiled = re.compile(_sql_regex_to_python(X.BANNED_RLIKE))
    assert compiled.search(phrase), phrase
    assert T.vocabulary_violations(phrase), phrase


@pytest.mark.parametrize("phrase", list(T.APPROVED_VOCABULARY) + [
    "Coverage raised, then a claim on the same line",
    "Rapid change cluster",
    "a similar maximum severity band",
    "Collision limit increased",
])
def test_e18_sql_regex_accepts_the_approved_vocabulary(phrase):
    compiled = re.compile(_sql_regex_to_python(X.BANNED_RLIKE))
    assert not compiled.search(phrase), phrase
    assert T.vocabulary_violations(phrase) == []


def test_e18_regex_is_built_from_the_one_authored_banned_list():
    for term in T.BANNED_VOCABULARY:
        assert term.replace(" ", r"\\s+") in X.BANNED_RLIKE


def test_e18_is_attached_to_every_user_facing_string_column():
    def _names(dataset):
        return " ".join(CATALOGUE[dataset])

    assert "E18" in _names("policy_pattern_match")
    assert "E18" in _names("policy_similarity")
    assert "E18" in _names("policy_timeline_event")
    assert "pattern_name" in " ".join(CATALOGUE["policy_pattern_match"].values())
    assert "evidence_summary" in " ".join(CATALOGUE["policy_pattern_match"].values())
    assert "top_reasons" in " ".join(CATALOGUE["policy_similarity"].values())
    assert "display_label" in " ".join(CATALOGUE["policy_timeline_event"].values())


# --- The severity cuts appear once ----------------------------------------

def test_severity_cuts_are_written_once_and_reused():
    """ADR-0008: ``next_claim_severity`` must come from the same cuts as
    ``severity_band``. In the SQL layer that means one CASE expression."""
    change_side = CATALOGUE["policy_change_event"][
        "E8_next_claim_severity_uses_the_documented_cuts"]
    claim_side = CATALOGUE["claim_event"][
        "E9_severity_band_partitions_the_amount_range"]
    assert X.SEVERITY_CASE.format(amount="next_claim_amount") in change_side
    assert X.SEVERITY_CASE.format(amount="settled_amount") in claim_side
    for band, _low, _high in T.SEVERITY_CUTS:
        assert f"'{band}'" in X.SEVERITY_CASE


def test_sql_severity_cuts_agree_with_the_python_bands():
    """Parse the numeric cuts back out of the SQL and compare them to
    :data:`transformations.SEVERITY_CUTS`."""
    thresholds = [int(m) for m in re.findall(r"< (\d+)", X.SEVERITY_CASE)]
    assert thresholds == [2500, 10000, 50000]
    assert [c[2] for c in T.SEVERITY_CUTS[:3]] == [2500.0, 10000.0, 50000.0]


# --- E4 names all seven linkage columns -----------------------------------

def test_e4_expectation_names_all_seven_linkage_columns():
    sql = CATALOGUE["policy_change_event"][
        "E4_linkage_columns_null_together_or_populated_together"]
    assert len(T.LINKAGE_COLUMNS) == 7
    for column in T.LINKAGE_COLUMNS:
        assert f"{column} IS NULL" in sql
        assert f"{column} IS NOT NULL" in sql


def test_e14_covers_every_pattern_code():
    for code in T.PATTERN_CODES:
        assert f"E14_flag_matches_a_row_for_{code}" in X.QA_PATTERN_CONSISTENCY


# --- The catalogue passes against the real fixture output -----------------

_PY_EQUIVALENTS = {
    "E4": lambda df: set(df[list(T.LINKAGE_COLUMNS)].notna().sum(axis=1).unique()) <= {0, 7},
    "E6": lambda df: (df["days_to_next_claim_report"].dropna() >= 0).all(),
    "E12": lambda df: set(
        df[df["change_category"] == "deductible"]["coverage_line"]
    ) <= set(T.DEDUCTIBLE_LINES),
}


@pytest.mark.parametrize("key", sorted(_PY_EQUIVALENTS))
def test_the_fixture_output_satisfies_the_catalogue(change_event, key):
    """The expectations are the tests (implementation plan, P2): the same
    invariants the pipeline enforces at write time hold on the fixture build."""
    assert _PY_EQUIVALENTS[key](change_event)
