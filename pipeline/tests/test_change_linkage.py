"""Claim linkage on ``policy_change_event`` — ADR-0004, expectations E4–E8.

The highest-risk work in the project: the signed loss delta and the seven-column
NULL propagation (implementation plan, P2).
"""

from __future__ import annotations

import pandas as pd
import pytest

import transformations as T
from conftest import D, row_by, rows_by


# --- next_claim_id is anchored on the REPORT date --------------------------

def test_linked_claim_is_first_by_report_date_not_loss_date(change_event):
    """P-10002 has two claims whose loss order and report order disagree.

    CLM-000202's loss is 26 days earlier than CLM-000201's, but its report is 14
    days later. Loss-date anchoring would pick CLM-000202; report-date anchoring
    picks CLM-000201, and that is the ruling (ADR-0004).
    """
    row = row_by(change_event, change_event_id="CHG-00000203")
    assert row["next_claim_id"] == "CLM-000201"


def test_next_claim_id_is_many_to_one_by_design(change_event):
    """Three changes on P-10001 — an address change, a coverage increase and its
    derived premium echo — all point at the same claim. Required for "several
    material changes before a high-severity claim"; not a duplication bug."""
    linked = rows_by(change_event, policy_id="P-10001", next_claim_id="CLM-000101")
    assert len(linked) == 3
    assert set(linked["change_event_id"]) == {
        "CHG-00000101", "CHG-00000102", "CHG-00000103"
    }
    assert linked["next_claim_id"].nunique() == 1


def test_change_after_the_last_report_is_unlinked(change_event):
    """P-10001's second coverage increase falls after the only claim's report
    date, so no claim is reported at or after it."""
    row = row_by(change_event, change_event_id="CHG-00000104")
    assert pd.isna(row["next_claim_id"])


# --- E4: all seven linkage columns NULL together or populated together -----

@pytest.mark.parametrize("change_event_id", ["CHG-00000104", "CHG-00000301",
                                             "CHG-00000302", "CHG-00000401"])
def test_unlinked_rows_have_all_seven_linkage_columns_null(change_event, change_event_id):
    row = row_by(change_event, change_event_id=change_event_id)
    for column in T.LINKAGE_COLUMNS:
        assert pd.isna(row[column]), f"{column} should be NULL on an unlinked row"


def test_change_timing_never_defaults_to_before_loss_on_an_unlinked_row(change_event):
    """If it did, ``change_timing = 'before_loss'`` would stop meaning
    "linked and before the loss" (ADR-0004)."""
    unlinked = change_event[change_event["next_claim_id"].isna()]
    assert len(unlinked) > 0
    assert unlinked["change_timing"].isna().all()


def test_e4_linkage_columns_null_together_or_populated_together(change_event):
    populated = change_event[list(T.LINKAGE_COLUMNS)].notna().sum(axis=1)
    assert set(populated.unique()) <= {0, len(T.LINKAGE_COLUMNS)}


# --- E5, E6, E7: the signed loss delta ------------------------------------

def test_e6_days_to_next_claim_report_is_never_negative(change_event):
    reported = change_event["days_to_next_claim_report"].dropna()
    assert len(reported) > 0
    assert (reported >= 0).all()


def test_e5_change_timing_domain_on_every_linked_row(change_event):
    linked = change_event[change_event["next_claim_id"].notna()]
    assert set(linked["change_timing"]) <= {"before_loss", "after_loss_before_report"}
    assert linked["change_timing"].notna().all()


def test_e7_sign_of_loss_delta_agrees_with_change_timing(change_event):
    linked = change_event[change_event["next_claim_id"].notna()]
    before = linked[linked["change_timing"] == "before_loss"]
    after = linked[linked["change_timing"] == "after_loss_before_report"]
    assert len(before) > 0 and len(after) > 0
    assert (before["days_to_next_claim_loss"] >= 0).all()
    assert (after["days_to_next_claim_loss"] < 0).all()


def test_loss_delta_is_signed_negative_inside_the_loss_report_gap(change_event):
    """P-10002's address change lands 6 days after the loss and 9 days before the
    report — the sequence report-date anchoring exists to make visible."""
    row = row_by(change_event, change_event_id="CHG-00000201")
    assert row["next_claim_id"] == "CLM-000201"
    assert row["days_to_next_claim_loss"] == -6
    assert row["days_to_next_claim_report"] == 9
    assert row["change_timing"] == "after_loss_before_report"


def test_loss_delta_is_positive_when_the_change_preceded_the_loss(change_event):
    row = row_by(change_event, change_event_id="CHG-00000101")
    assert row["days_to_next_claim_loss"] == 24
    assert row["days_to_next_claim_report"] == 29
    assert row["change_timing"] == "before_loss"


def test_bare_threshold_filter_would_admit_after_loss_changes(change_event):
    """The product's single most important Genie instruction, as a property.

    ``days_to_next_claim_loss <= 30`` silently admits after-loss changes; the
    canonical two-filter form does not (ADR-0004).
    """
    linked = change_event[change_event["next_claim_id"].notna()]
    bare = linked[linked["days_to_next_claim_loss"] <= 30]
    canonical = linked[(linked["change_timing"] == "before_loss")
                       & (linked["days_to_next_claim_loss"] <= 30)]
    assert len(bare) > len(canonical), (
        "the fixture must contain an after-loss change, or this instruction is untested"
    )
    assert (canonical["change_timing"] == "before_loss").all()


# --- Same-day ties (spec 02 §2, ADR-0004) ---------------------------------

def test_same_day_as_the_loss_is_before_loss_with_a_zero_delta(change_event):
    row = row_by(change_event, change_event_id="CHG-00001001")
    assert row["change_date"] == D(45)
    assert row["days_to_next_claim_loss"] == 0
    assert row["change_timing"] == "before_loss"
    assert row["days_to_next_claim_report"] == 5


def test_same_day_as_the_report_is_linked_with_a_zero_report_delta(change_event):
    row = row_by(change_event, change_event_id="CHG-00000202")
    assert row["next_claim_id"] == "CLM-000201"
    assert row["days_to_next_claim_report"] == 0
    assert row["days_to_next_claim_loss"] == -15
    assert row["change_timing"] == "after_loss_before_report"


# --- E8: severity is computed once and denormalised ------------------------

def test_e8_next_claim_severity_agrees_with_claim_event_severity_band(change_event, claim_event):
    bands = dict(zip(claim_event["claim_id"], claim_event["severity_band"]))
    linked = change_event[change_event["next_claim_id"].notna()]
    assert len(linked) > 0
    for _, row in linked.iterrows():
        assert row["next_claim_severity"] == bands[row["next_claim_id"]]


def test_next_claim_amount_and_line_are_denormalised_from_the_same_claim(change_event, claim_event):
    amounts = dict(zip(claim_event["claim_id"], claim_event["settled_amount"]))
    lines = dict(zip(claim_event["claim_id"], claim_event["coverage_line"]))
    linked = change_event[change_event["next_claim_id"].notna()]
    for _, row in linked.iterrows():
        assert row["next_claim_amount"] == amounts[row["next_claim_id"]]
        assert row["next_claim_coverage_line"] == lines[row["next_claim_id"]]


def test_change_relates_to_claimed_coverage(change_event):
    """``coverage_line = next_claim_coverage_line`` (ADR-0005). A change that is
    not line-specific reads False rather than NULL, so the column stays a usable
    two-valued filter on every linked row."""
    assert row_by(change_event, change_event_id="CHG-00000101")[
        "change_relates_to_claimed_coverage"] == True  # noqa: E712
    assert row_by(change_event, change_event_id="CHG-00000102")[
        "change_relates_to_claimed_coverage"] == False  # noqa: E712
    assert pd.isna(row_by(change_event, change_event_id="CHG-00000104")[
        "change_relates_to_claimed_coverage"])


# --- Tie-break when two claims share a report date -------------------------

def test_report_date_tie_is_broken_on_claim_id(anchor_date):
    changes = [{"change_event_id": "CHG-90000001", "policy_id": "P-90001",
                "endorsement_id": "END-90000001", "change_date": D(30),
                "change_category": "address", "coverage_line": None,
                "old_value": "a", "new_value": "b",
                "old_value_num": None, "new_value_num": None}]
    claims = [
        {"claim_id": "CLM-900002", "policy_id": "P-90001", "coverage_line": "COLL",
         "loss_date": D(25), "report_date": D(20), "settled_amount": 1000.0,
         "claim_status": "settled"},
        {"claim_id": "CLM-900001", "policy_id": "P-90001", "coverage_line": "BI",
         "loss_date": D(22), "report_date": D(20), "settled_amount": 5000.0,
         "claim_status": "settled"},
    ]
    history = [{"policy_id": "P-90001", "version_no": 1, "customer_id": "C-900001",
                "effective_from": D(400), "effective_to": None, "is_current": True,
                "garaging_state": "TX"}]
    built = T.build_policy_change_event(changes, claims, history, anchor_date)
    assert built.iloc[0]["next_claim_id"] == "CLM-900001"
