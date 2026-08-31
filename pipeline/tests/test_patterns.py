"""Noteworthy Patterns — ADR-0009, expectations E13 and E14.

The rules and the ``policy_profile`` booleans come from **one** rule evaluation
pass. ADR-0007 puts the generated SQL in the evidence panel, so a boolean that
says a rule fired while the match table holds no row is a disagreement visible on
screen.
"""

from __future__ import annotations

import pandas as pd

import transformations as T
from conftest import D, row_by, rows_by


def _codes_for(pattern_match, policy_id):
    return set(rows_by(pattern_match, policy_id=policy_id)["pattern_code"])


# --- The six rules, each fired by a planted policy ------------------------

def test_r1_coverage_raised_then_claimed_same_line(pattern_match):
    """Coverage increase, Linked Claim on the same Coverage Line within 60 days,
    ``before_loss``."""
    row = row_by(pattern_match, policy_id="P-10001",
                 pattern_code="coverage_raised_then_claimed_same_line")
    assert row["evidence_change_event_id"] == "CHG-00000101"
    assert row["evidence_claim_id"] == "CLM-000101"
    assert row["matched_on_date"] == D(41)


def test_r1_does_not_fire_when_the_claim_is_on_a_different_line(pattern_match, change_event):
    """P-10009 claims on BI with no coverage change at all; the rule needs the
    same-line conjunction, which is what makes it a finding not a coincidence."""
    assert "coverage_raised_then_claimed_same_line" not in _codes_for(pattern_match, "P-10009")


def test_r2_deductible_lowered_before_claim(pattern_match):
    row = row_by(pattern_match, policy_id="P-10006",
                 pattern_code="deductible_lowered_before_claim")
    assert row["evidence_change_event_id"] == "CHG-00000601"
    assert row["evidence_claim_id"] == "CLM-000601"


def test_r3_change_in_loss_report_gap(pattern_match):
    """Any material change with ``change_timing = 'after_loss_before_report'``."""
    row = row_by(pattern_match, policy_id="P-10002",
                 pattern_code="change_in_loss_report_gap")
    assert row["evidence_claim_id"] == "CLM-000201"


def test_r3_never_fires_on_a_policy_with_no_gap_change(pattern_match):
    assert "change_in_loss_report_gap" not in _codes_for(pattern_match, "P-10001")


def test_r4_rapid_change_cluster(pattern_match):
    """Three or more material changes within any 30-day span. P-10005 has four
    across 22 days."""
    row = row_by(pattern_match, policy_id="P-10005", pattern_code="rapid_change_cluster")
    assert row["matched_on_date"] == D(60)
    assert "4 material changes" in row["evidence_summary"]


def test_r4_does_not_fire_on_three_changes_spread_over_a_hundred_days(pattern_match):
    assert "rapid_change_cluster" not in _codes_for(pattern_match, "P-10003")


def test_r5_vehicle_and_address_within_60d(pattern_match):
    row = row_by(pattern_match, policy_id="P-10008",
                 pattern_code="vehicle_and_address_within_60d")
    assert row["evidence_change_event_id"] == "CHG-00000801"


def test_r6_claim_near_new_limit(pattern_match):
    """An ``at_or_near_limit`` claim where that line's limit rose within the
    prior 90 days — the two-axis conjunction of ADR-0008."""
    row = row_by(pattern_match, policy_id="P-10007", pattern_code="claim_near_new_limit")
    assert row["evidence_claim_id"] == "CLM-000701"
    assert row["evidence_change_event_id"] == "CHG-00000701"


def test_r6_does_not_fire_on_a_low_utilisation_claim(pattern_match):
    assert "claim_near_new_limit" not in _codes_for(pattern_match, "P-10010")


def test_every_rule_in_the_adr_fires_somewhere_in_the_fixture(pattern_match):
    assert set(pattern_match["pattern_code"]) == set(T.PATTERN_CODES)


def test_a_policy_can_match_several_patterns(pattern_match):
    assert _codes_for(pattern_match, "P-10005") == {
        "coverage_raised_then_claimed_same_line",
        "rapid_change_cluster",
        "vehicle_and_address_within_60d",
        "claim_near_new_limit",
    }


def test_a_policy_with_nothing_noteworthy_has_no_rows(pattern_match):
    assert _codes_for(pattern_match, "P-10004") == set()


# --- Grain -----------------------------------------------------------------

def test_grain_is_one_row_per_policy_times_pattern(pattern_match):
    assert not pattern_match.duplicated(subset=["policy_id", "pattern_code"]).any()


def test_every_match_carries_a_date_and_evidence(pattern_match):
    assert pattern_match["matched_on_date"].notna().all()
    assert pattern_match["evidence_summary"].notna().all()
    has_evidence = (pattern_match["evidence_change_event_id"].notna()
                    | pattern_match["evidence_claim_id"].notna())
    assert has_evidence.all()


def test_pattern_names_are_authored_not_derived_from_codes(pattern_match):
    for _, row in pattern_match.iterrows():
        assert row["pattern_name"] == T.PATTERN_NAMES[row["pattern_code"]]
        assert row["pattern_name"] != row["pattern_code"]


# --- E13 and E14: one pass, two representations ---------------------------

def test_e13_noteworthy_pattern_count_equals_distinct_pattern_codes(policy_profile, pattern_match):
    counts = (pattern_match.groupby("policy_id")["pattern_code"]
              .nunique().to_dict())
    for _, row in policy_profile.iterrows():
        assert row["noteworthy_pattern_count"] == counts.get(row["policy_id"], 0)


def test_e14_each_boolean_is_true_iff_a_matching_row_exists(policy_profile, pattern_match):
    for _, row in policy_profile.iterrows():
        codes = _codes_for(pattern_match, row["policy_id"])
        for code in T.PATTERN_CODES:
            assert bool(row[f"pattern_{code}"]) == (code in codes), (
                f"{row['policy_id']} disagrees on {code}"
            )


def test_nothing_noteworthy_is_a_count_of_zero_not_a_six_way_and_not(policy_profile):
    quiet = policy_profile[policy_profile["noteworthy_pattern_count"] == 0]
    assert len(quiet) > 0
    for column in T.PATTERN_FLAG_COLUMNS:
        assert (quiet[column] == False).all()  # noqa: E712


def test_adding_a_rule_would_not_change_the_existing_columns():
    """The column set is not the constraint (ADR-0009): every flag is derived by
    name from the code list, so a new rule adds a boolean and nothing else."""
    assert T.PATTERN_FLAG_COLUMNS == tuple(f"pattern_{c}" for c in T.PATTERN_CODES)
    profile_columns = {name for name, _ in T.POLICY_PROFILE_SCHEMA}
    assert set(T.PATTERN_FLAG_COLUMNS) <= profile_columns


def test_pattern_windows_are_baked_constants():
    """"Rapid change cluster" means something specific or it means nothing."""
    assert T.PATTERN_CLUSTER_SPAN_DAYS == 30
    assert T.PATTERN_CLUSTER_MIN_CHANGES == 3
    assert T.PATTERN_CLAIM_WINDOW_DAYS == 60
    assert T.PATTERN_VEHICLE_ADDRESS_DAYS == 60
    assert T.PATTERN_LIMIT_RAISED_WINDOW_DAYS == 90


def test_pattern_pass_is_deterministic(change_event, claim_event):
    first = T.build_policy_pattern_match(change_event, claim_event)
    second = T.build_policy_pattern_match(change_event, claim_event)
    pd.testing.assert_frame_equal(first, second)
