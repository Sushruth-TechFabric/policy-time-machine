"""``claim_event`` — ADR-0008 and ADR-0004, expectations E9, E10, E11.

This is the table for claim-level counting (spec 02 §3), and every prior-change
window on it is anchored on ``loss_date``.
"""

from __future__ import annotations

import pandas as pd
import pytest

import transformations as T
from conftest import D, row_by


# --- E9: severity bands partition the amount range ------------------------

@pytest.mark.parametrize("amount,band", [
    (0.0, "minor"), (2499.99, "minor"),
    (2500.0, "moderate"), (9999.99, "moderate"),
    (10000.0, "severe"), (49999.99, "severe"),
    (50000.0, "catastrophic"), (5_000_000.0, "catastrophic"),
])
def test_e9_severity_cuts_are_half_open_with_no_gap_and_no_overlap(amount, band):
    assert T.severity_band(amount) == band


def test_e9_every_claim_lands_in_exactly_one_band(claim_event):
    assert claim_event["severity_band"].notna().all()
    assert set(claim_event["severity_band"]) <= set(T.SEVERITY_ORDER)


def test_high_severity_is_severe_or_catastrophic_never_a_dollar_threshold():
    assert T.HIGH_SEVERITY_BANDS == ("severe", "catastrophic")
    assert T.is_high_severity("severe") and T.is_high_severity("catastrophic")
    assert not T.is_high_severity("moderate")


def test_severity_bands_are_populated_across_the_range(claim_event):
    assert set(claim_event["severity_band"]) >= {"minor", "moderate", "severe", "catastrophic"}


# --- E10: limit utilisation ------------------------------------------------

def test_e10_utilization_is_null_when_the_limit_is_zero(claim_event):
    row = row_by(claim_event, claim_id="CLM-001101")
    assert row["applicable_limit"] == 0.0
    assert pd.isna(row["limit_utilization_pct"])
    assert pd.isna(row["at_or_near_limit"])


def test_e10_utilization_above_100_is_permitted_and_never_clamped(claim_event):
    """A $60,000 loss against a $40,000 limit. Clamping would hide exactly the
    near-limit stories the axis exists to tell (ADR-0008)."""
    row = row_by(claim_event, claim_id="CLM-000501")
    assert row["limit_utilization_pct"] == 150.0
    assert row["at_or_near_limit"] == True  # noqa: E712


def test_e10_utilization_is_recomputable_from_the_stored_columns(claim_event):
    known = claim_event[claim_event["limit_utilization_pct"].notna()]
    for _, row in known.iterrows():
        expected = float(row["settled_amount"]) / float(row["applicable_limit"]) * 100.0
        assert abs(float(row["limit_utilization_pct"]) - expected) < 1e-6


def test_at_or_near_limit_uses_the_named_constant(claim_event):
    assert T.AT_OR_NEAR_LIMIT_PCT == 90.0
    known = claim_event[claim_event["limit_utilization_pct"].notna()]
    for _, row in known.iterrows():
        assert bool(row["at_or_near_limit"]) == (
            float(row["limit_utilization_pct"]) >= T.AT_OR_NEAR_LIMIT_PCT
        )


def test_the_two_axes_stay_independent(claim_event):
    """ADR-0008's signature conjunction: modest dollars, near-limit utilisation."""
    row = row_by(claim_event, claim_id="CLM-000701")
    assert row["severity_band"] == "moderate"
    assert row["limit_utilization_pct"] == 97.0
    assert row["at_or_near_limit"] == True  # noqa: E712


def test_applicable_limit_is_read_at_the_loss_date_not_now(claim_event):
    """P-10010's COLL limit rose to 15,000 on the day of the loss; the SCD2
    version covering the loss date is the one that applies."""
    assert row_by(claim_event, claim_id="CLM-001001")["applicable_limit"] == 15000.0
    # P-10005's limit rose 51 days before the loss, so the new limit applies.
    assert row_by(claim_event, claim_id="CLM-000501")["applicable_limit"] == 40000.0


# --- E11: report_date >= loss_date ----------------------------------------

def test_e11_report_date_is_never_before_the_loss_date(claim_event):
    for _, row in claim_event.iterrows():
        assert row["report_date"] >= row["loss_date"]
    assert (claim_event["loss_to_report_days"] >= 0).all()


def test_loss_to_report_days_matches_the_two_dates(claim_event):
    for _, row in claim_event.iterrows():
        assert row["loss_to_report_days"] == (row["report_date"] - row["loss_date"]).days


# --- Prior-change context, all anchored on loss_date ----------------------

def test_prior_windows_are_anchored_on_the_loss_date(claim_event):
    row = row_by(claim_event, claim_id="CLM-000501")
    # Four material changes at 82, 75, 68 and 60 days before the anchor; the loss
    # is at 31 days. Only the status change at 60 falls inside 30 days of the loss.
    assert row["material_changes_prior_30d"] == 1
    assert row["material_changes_prior_60d"] == 4
    assert row["material_changes_prior_90d"] == 4


def test_a_change_on_the_day_of_the_loss_counts_as_prior(claim_event):
    """ADR-0004 rules a same-day change ``before_loss``; the claim-side windows
    must agree, or the two tables would answer the same question differently."""
    row = row_by(claim_event, claim_id="CLM-001001")
    assert row["material_changes_prior_30d"] == 1
    assert row["days_since_last_material_change_before_loss"] == 0


def test_material_changes_in_loss_report_gap(claim_event):
    """Gap questions answerable at claim grain rather than only from the change
    table (ADR-0004). The gap is ``(loss_date, report_date]``: a change on the
    report date is still inside it, a change on the loss date is not."""
    row = row_by(claim_event, claim_id="CLM-000201")
    assert row["material_changes_in_loss_report_gap"] == 2
    # A change on the day of the loss is *before* the loss, not inside the gap.
    assert row_by(claim_event, claim_id="CLM-001001")[
        "material_changes_in_loss_report_gap"] == 0


def test_gap_count_agrees_with_change_side_timing(change_event, claim_event):
    """The two tables must agree on the same fact."""
    for _, claim in claim_event.iterrows():
        from_changes = change_event[
            (change_event["next_claim_id"] == claim["claim_id"])
            & (change_event["change_timing"] == "after_loss_before_report")
            & (change_event["is_material"] == True)  # noqa: E712
        ]
        # Every gap change linked to this claim is counted by the claim-side
        # column (the claim-side column may count more, since a change can fall
        # in the gap of a claim that is not its Linked Claim).
        assert len(from_changes) <= claim["material_changes_in_loss_report_gap"]


def test_last_material_change_before_loss(claim_event):
    row = row_by(claim_event, claim_id="CLM-000101")
    assert row["last_material_change_category"] == "coverage"
    assert row["last_material_change_date"] == D(41)
    assert row["days_since_last_material_change_before_loss"] == 24


def test_no_prior_change_context_when_there_are_no_changes(claim_event):
    row = row_by(claim_event, claim_id="CLM-000901")
    assert row["material_changes_prior_90d"] == 0
    assert pd.isna(row["days_since_last_material_change_before_loss"])
    assert pd.isna(row["last_material_change_category"])
    assert row["relevant_coverage_change_prior_60d"] == False  # noqa: E712


def test_relevant_change_is_same_line_coverage_or_deductible(claim_event):
    """CONTEXT.md: a Relevant Change is a coverage *or deductible* change on the
    same Coverage Line the Linked Claim was later filed against."""
    # Coverage increase on COLL, 24 days before a COLL loss.
    assert row_by(claim_event, claim_id="CLM-000101")[
        "relevant_coverage_change_prior_60d"] == True  # noqa: E712
    # Deductible cut on COMP, 32 days before a COMP loss.
    assert row_by(claim_event, claim_id="CLM-000601")[
        "relevant_coverage_change_prior_60d"] == True  # noqa: E712
    # P-10002's only prior change is on COLL but 36 days before a COLL loss —
    # relevant. Its second claim's prior change is 10 days before that loss.
    assert row_by(claim_event, claim_id="CLM-000201")[
        "relevant_coverage_change_prior_60d"] == True  # noqa: E712


def test_claim_event_is_one_row_per_claim(claim_event, sources):
    assert len(claim_event) == len(sources["claims"])
    assert claim_event["claim_id"].is_unique
