"""Generator tests.

The determinism obligations of spec 01 section 10 are the reason this file
exists. Everything else here guards a rule that fails silently: a date literal
that pins a story to a calendar, an identifier the application cannot detect, or
a word the product has committed not to use.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from generator import build
from generator import constants as K
from generator import validate as validation
from generator.__main__ import main as generator_main
from generator.emit import DATE_COLUMNS, POLICY_COLUMNS, TABLE_ORDER, assert_source_invariants
from generator.ids import assert_lexical_reservation, contains_policy_reference

SEED = 42
ANCHOR_SHIFT_DAYS = 37
YEAR_CROSSING_SHIFT_DAYS = 400
SOURCE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def anchors() -> tuple[dt.date, dt.date]:
    today = dt.datetime.now(dt.timezone.utc).date()
    return today, today - dt.timedelta(days=ANCHOR_SHIFT_DAYS)


@pytest.fixture(scope="module")
def dataset(anchors):
    return build(SEED, anchors[0])


@pytest.fixture(scope="module")
def shifted(anchors):
    return build(SEED, anchors[1])


@pytest.fixture(scope="module")
def year_shifted(anchors):
    return build(SEED, anchors[0] - dt.timedelta(days=YEAR_CROSSING_SHIFT_DAYS))


def assert_same_stories(later_frames, earlier_frames, later: dt.date, earlier: dt.date) -> None:
    """Every table identical once the earlier run's dates are shifted forward."""
    shift = pd.Timedelta(days=(later - earlier).days)
    year_delta = later.year - earlier.year
    far_future = pd.Timestamp(K.FAR_FUTURE)

    assert set(later_frames) == set(earlier_frames)
    for table in TABLE_ORDER:
        a, b = later_frames[table], earlier_frames[table]
        assert list(a.columns) == list(b.columns), table
        assert len(a) == len(b), f"{table}: row count moved with the anchor"
        for column in a.columns:
            left, right = a[column].reset_index(drop=True), b[column].reset_index(drop=True)
            if column in DATE_COLUMNS[table]:
                open_ended = left.eq(far_future)
                assert open_ended.equals(right.eq(far_future)), f"{table}.{column}"
                assert left.isna().equals(right.isna()), f"{table}.{column}"
                comparable = ~open_ended & left.notna()
                delta = (left[comparable] - right[comparable]).unique()
                assert list(delta) == [shift], f"{table}.{column} did not shift by the anchor delta"
            elif column in ("birth_year", "model_year"):
                # Ages are relative to the anchor, so a year-crossing shift moves
                # the stored year by exactly the year delta and nothing else.
                assert (left - right).eq(year_delta).all(), f"{table}.{column}"
            else:
                pd.testing.assert_series_equal(left, right, check_names=False)


# ------------------------------------------------------- determinism (section 10)
def test_same_seed_different_anchor_tells_the_same_stories(dataset, shifted, anchors):
    """Identical stories at shifted dates - spec 01 section 10 rule 3."""
    assert_same_stories(dataset, shifted, anchors[0], anchors[1])


def test_determinism_survives_a_year_boundary(dataset, year_shifted, anchors):
    """The shift is larger than a year, so the year-derived attributes move too."""
    earlier = anchors[0] - dt.timedelta(days=YEAR_CROSSING_SHIFT_DAYS)
    assert earlier.year < anchors[0].year
    assert_same_stories(dataset, year_shifted, anchors[0], earlier)


def test_same_seed_same_anchor_is_idempotent(dataset, anchors):
    again = build(SEED, anchors[0])
    for table in TABLE_ORDER:
        pd.testing.assert_frame_equal(dataset[table], again[table])


def test_identity_is_owned_by_the_seed(dataset, shifted):
    """Identifiers and scenario membership do not move with the anchor."""
    assert list(dataset["policy_history"]["policy_id"]) == list(shifted["policy_history"]["policy_id"])
    pd.testing.assert_frame_equal(dataset["scenario_assignment"], shifted["scenario_assignment"])
    assert (
        dataset["generation_manifest"]["demo_policy_id"].iloc[0]
        == shifted["generation_manifest"]["demo_policy_id"].iloc[0]
    )


# -------------------------------------------------------- no absolute date literals
def test_no_absolute_date_literal_in_the_generator():
    """Spec 01 section 5 rule 1 and section 10 rule 2.

    The one permitted value is the SCD2 open-ended attribute sentinel, which the
    specification names explicitly. Everything else must be anchor plus offset.
    """
    patterns = (
        re.compile(r"\d{4}-\d{2}-\d{2}"),
        re.compile(r"\b(?:date|datetime)\s*\(\s*\d{4}"),
        re.compile(r"Timestamp\(\s*['\"]?\d{4}"),
    )
    offenders = []
    for path in sorted(SOURCE_DIR.glob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if "permitted attribute sentinel" in line:
                continue
            if any(pattern.search(line) for pattern in patterns):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "absolute date literals found:\n" + "\n".join(offenders)


# ------------------------------------------------------------ identifier contract
def test_identifier_formats(dataset):
    expectations = {
        ("policy_history", "policy_id"): r"^P-\d{5}$",
        ("customer", "customer_id"): r"^C-\d{6}$",
        ("claim", "claim_id"): r"^CLM-\d{6}$",
        ("vehicle", "vehicle_id"): r"^VEH-\d{6}$",
        ("agent", "agent_id"): r"^AGT-\d{4}$",
    }
    for (table, column), pattern in expectations.items():
        series = dataset[table][column].dropna()
        assert series.str.fullmatch(pattern).all(), f"{table}.{column} format"
        assert series.is_unique or table == "policy_history", f"{table}.{column} uniqueness"

    endorsements = dataset["policy_history"]["endorsement_id"].dropna()
    assert endorsements.str.fullmatch(r"^END-\d{8}$").all()
    payments = dataset["claim_payment"]["payment_id"]
    assert payments.is_unique and payments.str.fullmatch(r"^PMT-\d{8}$").all()


def test_lexical_reservation_holds(dataset):
    assert_lexical_reservation(dataset, POLICY_COLUMNS)
    assert contains_policy_reference("see P-18492 please")
    assert not contains_policy_reference("CLM-002317")


# ------------------------------------------------------------------ SCD2 shape
def test_source_invariants(dataset, anchors):
    assert_source_invariants(dataset, anchors[0])


def test_scd2_versions_are_contiguous_and_non_overlapping(dataset):
    for table, keys in (
        ("policy_history", ["policy_id"]),
        ("policy_coverage_history", ["policy_id", "coverage_line"]),
    ):
        frame = dataset[table].sort_values(keys + ["version_no"], kind="stable")
        group = frame.groupby(keys, sort=False)
        assert (group.cumcount() + 1 == frame["version_no"]).all(), f"{table}: version_no is not dense"
        previous_to = group["effective_to"].shift(1)
        overlap = frame["effective_from"].lt(previous_to)
        gap = frame["effective_from"].gt(previous_to)
        assert not overlap.any() and not gap.any(), f"{table}: versions are not contiguous"
        current = frame.loc[frame["is_current"]]
        assert current["effective_to"].eq(pd.Timestamp(K.FAR_FUTURE)).all()
        assert len(current) == len(group.size())


def test_deductibles_exist_only_on_collision_and_comprehensive(dataset):
    coverage = dataset["policy_coverage_history"]
    with_deductible = coverage.loc[coverage["deductible_amount"].notna(), "coverage_line"].unique()
    assert set(with_deductible) == set(K.DEDUCTIBLE_LINES)
    without = coverage.loc[~coverage["coverage_line"].isin(K.DEDUCTIBLE_LINES)]
    assert without["deductible_amount"].isna().all()


# ------------------------------------------------------------------ temporal rules
def test_no_event_date_exceeds_the_anchor(dataset, anchors):
    anchor = pd.Timestamp(anchors[0])
    events = {
        "policy_history": ["effective_from"],
        "policy_coverage_history": ["effective_from"],
        "vehicle": ["added_date", "removed_date"],
        "claim": ["loss_date", "report_date"],
        "claim_payment": ["payment_date"],
    }
    for table, columns in events.items():
        for column in columns:
            assert dataset[table][column].dropna().le(anchor).all(), f"{table}.{column}"
    # Attribute dates legitimately sit in the future; clamping them would make
    # every policy look expired (ADR-0006).
    assert dataset["policy_history"]["term_end_date"].gt(anchor).any()


def test_loss_to_report_lag_is_never_zero_and_never_uniform(dataset):
    claim = dataset["claim"]
    lag = (claim["report_date"] - claim["loss_date"]).dt.days
    assert lag.min() >= K.REPORT_LAG_MIN_DAYS
    assert lag.max() <= K.REPORT_LAG_CAP_DAYS
    assert 3 <= lag.median() <= 5
    assert 16 <= lag.quantile(0.90) <= 26
    # Lognormal, not uniform: the mean sits well above the median.
    assert lag.mean() > lag.median() * 1.4


def test_activity_tail_reaches_the_staleness_budget(dataset, anchors):
    anchor = pd.Timestamp(anchors[0])
    claim = dataset["claim"]
    boundary = anchor - pd.Timedelta(days=K.ACTIVITY_TAIL_DAYS)
    assert claim["loss_date"].ge(boundary).sum() > 100
    history = dataset["policy_history"]
    assert history["effective_from"].ge(boundary).sum() > 500


# ------------------------------------------------------------------ change rules
def test_renewals_do_not_recalculate_status(dataset):
    """Spec 01 section 6 rule 2 - the premium-echo problem's side door.

    A version with no `endorsement_id` was committed by a renewal alone. It may
    move the term dates and the premium; if it also moved the status, the
    pipeline would derive a status change event from it, and renewal-driven
    status would be back in the material counts through a side door.
    """
    history = dataset["policy_history"].sort_values(["policy_id", "version_no"], kind="stable")
    group = history.groupby("policy_id", sort=False)
    renewal_only = (
        history["endorsement_id"].isna()
        & history["term_start_date"].ne(group["term_start_date"].shift(1))
        & group["term_start_date"].shift(1).notna()
    )
    assert renewal_only.sum() > 1_000, "no pure renewal versions to check"
    for column in ("policy_status", "garaging_postal_code", "primary_vehicle_id", "agent_id"):
        moved = history[column].ne(group[column].shift(1)) & group[column].shift(1).notna()
        assert not (renewal_only & moved).any(), f"a renewal moved {column}"


def test_premium_moves_accompany_coverage_changes(dataset):
    """Spec 01 section 6 rule 1: a coverage change carries a derived premium move.

    The premium move is visible in the history and is never counted as material;
    materiality is asserted in the semantic layer, not here.
    """
    coverage = dataset["policy_coverage_history"].sort_values(
        ["policy_id", "coverage_line", "version_no"], kind="stable"
    )
    group = coverage.groupby(["policy_id", "coverage_line"], sort=False)
    moved = coverage["limit_amount"].ne(group["limit_amount"].shift(1)) & group[
        "limit_amount"
    ].shift(1).notna()
    changed = coverage.loc[moved, ["policy_id", "effective_from"]].drop_duplicates()

    history = dataset["policy_history"].sort_values(["policy_id", "version_no"], kind="stable")
    hgroup = history.groupby("policy_id", sort=False)
    history = history.assign(previous_premium=hgroup["annual_premium"].shift(1))
    joined = changed.merge(
        history, left_on=["policy_id", "effective_from"], right_on=["policy_id", "effective_from"]
    )
    assert len(joined) == len(changed), "a coverage change has no policy version on the same day"
    premium_moved = joined["annual_premium"].ne(joined["previous_premium"])
    assert premium_moved.mean() > 0.95


def test_status_categories_are_the_declared_set(dataset):
    statuses = set(dataset["policy_history"]["policy_status"].unique())
    assert statuses.issubset(set(K.POLICY_STATUSES))
    assert {"active", "lapsed", "reinstated"}.issubset(statuses)
    assert statuses & {"cancelled", "non_renewed"}


# ------------------------------------------------------------------ claim rules
def test_every_severity_band_is_populated(dataset):
    amounts = dataset["claim"]["settled_amount"]
    for band, low, high in K.SEVERITY_BANDS:
        count = int(((amounts >= low) & (amounts < high)).sum())
        assert count > 0, f"severity band {band} is empty"


def test_payments_sum_to_settled_amount_on_settled_claims(dataset):
    claim = dataset["claim"]
    paid = dataset["claim_payment"].groupby("claim_id")["amount"].sum()
    settled = claim.loc[claim["claim_status"] == "settled"].set_index("claim_id")["settled_amount"]
    joined = settled.to_frame("settled").join(paid.to_frame("paid"))
    assert joined["paid"].notna().all()
    assert np.allclose(joined["paid"], joined["settled"], atol=0.011)


def test_claims_are_filed_against_one_known_coverage_line(dataset):
    lines = set(dataset["claim"]["coverage_line"].unique())
    assert lines.issubset(set(K.COVERAGE_LINES))


# ------------------------------------------------------------------ scenarios
def test_scenario_catalogue_sizes(dataset):
    counts = dataset["scenario_assignment"]["scenario_id"].value_counts()
    for scenario, size in K.SCENARIO_SIZES.items():
        assert counts.get(scenario, 0) == size, scenario
    assert counts.get("DEMO", 0) == 1


def test_scenario_populations_are_disjoint(dataset):
    assignment = dataset["scenario_assignment"]
    catalogue = assignment[assignment["scenario_id"] != "DEMO"]
    assert catalogue["policy_id"].is_unique


# ------------------------------------------------------------------ vocabulary
def test_no_banned_vocabulary_anywhere_in_the_generator():
    """Spec 01 section 11 and ADR-0014.

    The boundary is enforced in code as well as in data: a comment that reaches
    for the wrong word is how the wrong word reaches a user template later.
    """
    banned = re.compile(
        r"\b(fraud\w*|suspicious|suspicion|red[ -]flags?|anomal\w+|risk scor\w+)\b",
        re.IGNORECASE,
    )
    offenders = []
    # Top-level modules only: this file necessarily spells the banned words in
    # order to look for them.
    for path in sorted(SOURCE_DIR.glob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if banned.search(line):
                offenders.append(f"{path.relative_to(SOURCE_DIR)}:{number}: {line.strip()}")
    assert not offenders, "banned vocabulary found:\n" + "\n".join(offenders)


# ------------------------------------------------------------- end to end
def test_cli_writes_every_table_and_validation_passes(tmp_path, anchors):
    """The gate the regeneration Workflow runs: generate, then validate."""
    out = tmp_path / "raw"
    exit_code = generator_main(
        ["--seed", str(SEED), "--anchor-date", anchors[0].isoformat(), "--out", str(out)]
    )
    assert exit_code == 0
    for table in TABLE_ORDER:
        assert (out / f"{table}.parquet").exists(), table

    report, measurements = validation.run(out)
    failed = [check.name for check in report.checks if not check.passed]
    assert not failed, f"validation failed: {failed}\n{report.render()}"
    assert measurements["category_ranking"] == K.CATEGORY_RANKING


def test_no_banned_vocabulary_in_emitted_strings(dataset):
    banned = re.compile(
        r"\b(fraud\w*|suspicious|red[ -]flags?|anomal\w+)\b",
        re.IGNORECASE,
    )
    for table, frame in dataset.items():
        for column in frame.columns:
            if frame[column].dtype != object:
                continue
            values = frame[column].dropna().astype(str).unique()
            assert not any(banned.search(value) for value in values), f"{table}.{column}"
