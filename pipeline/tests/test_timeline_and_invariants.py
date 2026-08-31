"""``policy_timeline_event`` plus the cross-table expectations E17, E18 and E19.

E20 is a schema review rather than a row property; it lives in
``test_profile.py`` and in the header comment of ``dlt_pipeline.py``.
"""

from __future__ import annotations

import datetime as _dt
import re

import pandas as pd
import pytest

import transformations as T
from conftest import D, row_by, rows_by


# --- policy_timeline_event -------------------------------------------------

def test_timeline_carries_every_change_claim_and_payment(timeline_event, sources):
    counts = timeline_event["event_type"].value_counts().to_dict()
    changes = sources["changes"]
    non_status = (changes["change_category"] != "status").sum()
    status = (changes["change_category"] == "status").sum()
    assert counts["policy_change"] == non_status
    assert counts["status_change"] == status
    assert counts["claim_filed"] == len(sources["claims"])
    assert counts["claim_payment"] == len(sources["claim_payment"])
    assert counts["policy_created"] == sources["policy_history"]["policy_id"].nunique()


def test_event_type_domain(timeline_event):
    assert set(timeline_event["event_type"]) <= set(T.TIMELINE_EVENT_TYPES)


def test_renewal_is_a_timeline_event_never_a_policy_change(timeline_event, change_event):
    """Renewal-driven recalculations are never emitted as change events — the
    premium-echo problem re-entering through a side door (spec 01 §6)."""
    renewals = rows_by(timeline_event, event_type="renewal")
    assert len(renewals) == 1
    assert renewals.iloc[0]["policy_id"] == "P-10005"
    assert renewals.iloc[0]["event_date"] == D(135)
    assert "renewal" not in set(change_event["change_category"])


def test_claim_is_placed_on_the_report_date_with_the_gap_in_the_label(timeline_event):
    """The only placement under which a change inside the Loss-to-Report Gap
    renders before the claim marker — the story scenario S3 exists to show."""
    claim = row_by(timeline_event, timeline_event_id="TLE-K-CLM-000201")
    assert claim["event_date"] == D(19)
    assert claim["display_label"] == "Collision claim reported 15 days after the loss"
    gap_change = row_by(timeline_event, timeline_event_id="TLE-C-CHG-00000201")
    assert gap_change["event_date"] < claim["event_date"]


def test_endorsement_grouping_is_available_to_the_ui(timeline_event):
    """One customer interaction, two deltas on one card (ADR-0003)."""
    grouped = rows_by(timeline_event, endorsement_id="END-00000001")
    assert len(grouped) == 2
    assert grouped["event_date"].nunique() == 1


def test_display_labels_are_pre_rendered(timeline_event):
    assert timeline_event["display_label"].notna().all()
    assert row_by(timeline_event, timeline_event_id="TLE-C-CHG-00000101")[
        "display_label"] == "Collision limit increased"
    assert row_by(timeline_event, timeline_event_id="TLE-C-CHG-00000601")[
        "display_label"] == "Comprehensive deductible decreased"


def test_amount_is_a_claim_or_payment_amount_only(timeline_event):
    with_amount = timeline_event[timeline_event["amount"].notna()]
    assert set(with_amount["event_type"]) == {"claim_filed", "claim_payment"}


def test_is_material_mirrors_the_change_table(timeline_event, change_event):
    materiality = dict(zip(change_event["change_event_id"], change_event["is_material"]))
    changes = timeline_event[timeline_event["event_type"].isin(
        ["policy_change", "status_change"])]
    for _, row in changes.iterrows():
        assert bool(row["is_material"]) == bool(materiality[row["source_id"]])


def test_timeline_mixes_grains_so_it_must_never_be_aggregated(timeline_event):
    """Documented in the table comment; asserted here as the reason. Counting
    material changes over this table would double-count nothing but would count
    claims and payments as policy history."""
    one_policy = rows_by(timeline_event, policy_id="P-10001")
    assert one_policy["event_type"].nunique() > 1


def test_timeline_is_ordered_for_reading_one_story(timeline_event):
    for _, group in timeline_event.groupby("policy_id"):
        dates = list(group["event_date"])
        assert dates == sorted(dates)


def test_timeline_event_id_is_unique_and_stable(timeline_event):
    assert timeline_event["timeline_event_id"].is_unique
    assert timeline_event["timeline_event_id"].str.startswith("TLE-").all()


# --- E17: no event date exceeds anchor_date -------------------------------

def _event_dates(curated):
    yield "policy_change_event.change_date", curated["policy_change_event"]["change_date"]
    yield "claim_event.loss_date", curated["claim_event"]["loss_date"]
    yield "claim_event.report_date", curated["claim_event"]["report_date"]
    yield "policy_timeline_event.event_date", curated["policy_timeline_event"]["event_date"]
    yield "policy_pattern_match.matched_on_date", curated["policy_pattern_match"]["matched_on_date"]
    yield "policy_profile.last_material_change_date", curated["policy_profile"]["last_material_change_date"]
    yield "policy_profile.last_claim_date", curated["policy_profile"]["last_claim_date"]


def test_e17_no_event_date_exceeds_the_anchor(curated, anchor_date):
    for name, series in _event_dates(curated):
        values = [v for v in series if pd.notna(v)]
        assert values, f"{name} is empty; E17 would be vacuous"
        assert max(values) <= anchor_date, name


def test_attribute_dates_may_legitimately_sit_in_the_future(policy_profile, anchor_date):
    """``term_end_date`` is an attribute date, not an event timestamp. Clamping
    it would make every policy look expired (spec 01 §5 rule 2)."""
    future = [d for d in policy_profile["term_end_date"] if pd.notna(d) and d > anchor_date]
    assert future


# --- E18: the no-fraud-labelling boundary as a data constraint ------------

_USER_FACING = (
    ("policy_pattern_match", "pattern_name"),
    ("policy_pattern_match", "evidence_summary"),
    ("policy_similarity", "top_reasons"),
    ("policy_timeline_event", "display_label"),
)


@pytest.mark.parametrize("table,column", _USER_FACING)
def test_e18_no_user_facing_string_uses_a_banned_term(curated, table, column):
    for value in curated[table][column]:
        assert T.vocabulary_violations(value) == [], f"{table}.{column}: {value!r}"


@pytest.mark.parametrize("phrase", [
    "possible fraud", "a suspicious change", "this predicts a claim",
    "raises the risk score", "an anomaly", "a red flag",
])
def test_e18_detects_the_terms_it_is_meant_to_catch(phrase):
    assert T.vocabulary_violations(phrase) != []


def test_e18_does_not_reject_the_approved_vocabulary():
    for term in T.APPROVED_VOCABULARY:
        assert T.vocabulary_violations(term) == []


def test_pattern_names_make_no_assertion_about_a_person():
    joined = " ".join(T.PATTERN_NAMES.values()).lower()
    for word in ("customer", "policyholder", "driver", "insured", "they", "he", "she"):
        assert not re.search(rf"\b{word}\b", joined), word


# --- E19: the identifier lexical reservation ------------------------------

_ID_COLUMNS = (
    ("policy_change_event", "change_event_id"),
    ("policy_change_event", "endorsement_id"),
    ("policy_change_event", "customer_id"),
    ("policy_change_event", "next_claim_id"),
    ("claim_event", "claim_id"),
    ("claim_event", "customer_id"),
    ("policy_timeline_event", "timeline_event_id"),
    ("policy_timeline_event", "endorsement_id"),
    ("policy_pattern_match", "evidence_change_event_id"),
    ("policy_pattern_match", "evidence_claim_id"),
    ("policy_profile", "customer_id"),
    ("policy_profile", "current_primary_vehicle"),
)


@pytest.mark.parametrize("table,column", _ID_COLUMNS)
def test_e19_no_non_policy_identifier_matches_the_policy_pattern(curated, table, column):
    for value in curated[table][column]:
        assert not T.matches_policy_id_pattern(value), f"{table}.{column}: {value!r}"


def test_e19_policy_id_columns_do_match_the_pattern(curated):
    """The reservation exists so the app's regex routes correctly (ADR-0007), so
    the policy columns themselves must match."""
    for table in curated:
        if "policy_id" in curated[table].columns:
            values = [v for v in curated[table]["policy_id"] if pd.notna(v)]
            assert values and all(T.matches_policy_id_pattern(v) for v in values), table


def test_e19_timeline_ids_do_not_embed_the_policy_id(timeline_event):
    created = rows_by(timeline_event, event_type="policy_created")
    assert len(created) > 0
    for _, row in created.iterrows():
        assert not T.matches_policy_id_pattern(row["timeline_event_id"])
        # The source_id on a policy_created row *is* a policy id, which E19 permits.
        assert row["source_id"] == row["policy_id"]


def test_policy_token_helper_strips_the_reserved_prefix():
    assert T._policy_token("P-18492") == "18492"
    assert not T.matches_policy_id_pattern(f"TLE-N-{T._policy_token('P-18492')}")


# --- Schemas ---------------------------------------------------------------

@pytest.mark.parametrize("table", list(T.SCHEMAS))
def test_every_table_matches_its_declared_schema(curated, table):
    assert list(curated[table].columns) == [n for n, _ in T.SCHEMAS[table]]


def test_the_genie_space_is_exactly_six_tables(curated):
    assert set(curated) == {
        "policy_change_event", "claim_event", "policy_profile",
        "policy_timeline_event", "policy_pattern_match", "policy_similarity",
    }


def test_no_scd2_column_leaks_into_the_genie_space(curated):
    """The SCD Type 2 tables are never exposed to Genie (ADR-0002)."""
    for table, df in curated.items():
        for column in ("version_no", "effective_from", "effective_to", "is_current"):
            assert column not in df.columns, f"{table}.{column}"


def test_the_whole_build_is_deterministic(sources, anchor_date):
    first = T.build_all(
        changes=sources["changes"], claims=sources["claims"],
        policy_history=sources["policy_history"],
        policy_coverage_history=sources["policy_coverage_history"],
        claim_payment=sources["claim_payment"], anchor_date=anchor_date, k=5)
    second = T.build_all(
        changes=sources["changes"], claims=sources["claims"],
        policy_history=sources["policy_history"],
        policy_coverage_history=sources["policy_coverage_history"],
        claim_payment=sources["claim_payment"], anchor_date=anchor_date, k=5)
    for table in first:
        pd.testing.assert_frame_equal(first[table], second[table])


def test_regeneration_at_a_different_anchor_shifts_dates_not_stories(sources):
    """ADR-0006: the same seed at a different anchor produces the same stories at
    different dates. Simulated here by shifting every source date by 10 days."""
    shift = _dt.timedelta(days=10)

    def _shift(df):
        out = df.copy()
        for column in out.columns:
            if "date" in column or column in ("effective_from", "effective_to"):
                out[column] = [
                    v + shift if isinstance(v, _dt.date) and v.year != 9999 else v
                    for v in out[column]
                ]
        return out

    shifted = {k: _shift(v) for k, v in sources.items()}
    base = T.build_all(
        changes=sources["changes"], claims=sources["claims"],
        policy_history=sources["policy_history"],
        policy_coverage_history=sources["policy_coverage_history"],
        claim_payment=sources["claim_payment"],
        anchor_date=_dt.date(2025, 6, 30), k=5)
    moved = T.build_all(
        changes=shifted["changes"], claims=shifted["claims"],
        policy_history=shifted["policy_history"],
        policy_coverage_history=shifted["policy_coverage_history"],
        claim_payment=shifted["claim_payment"],
        anchor_date=_dt.date(2025, 6, 30) + shift, k=5)

    # The relationships are identical; only the dates moved.
    for column in ("days_to_next_claim_loss", "days_to_next_claim_report",
                   "change_timing", "nearest_address_change_offset_days"):
        assert list(base["policy_change_event"][column].astype(str)) == \
            list(moved["policy_change_event"][column].astype(str))
    pd.testing.assert_frame_equal(
        base["policy_pattern_match"].drop(columns=["matched_on_date"]),
        moved["policy_pattern_match"].drop(columns=["matched_on_date"]))
    pd.testing.assert_frame_equal(base["policy_similarity"], moved["policy_similarity"])
