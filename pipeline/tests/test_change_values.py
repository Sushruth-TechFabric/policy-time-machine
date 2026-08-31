"""Typed values, direction, percentage, category proximity and prior-window
context on ``policy_change_event`` — ADR-0003, expectations E1, E2, E3, E12."""

from __future__ import annotations

import math

import pandas as pd
import pytest

import transformations as T
from conftest import D, row_by, rows_by


# --- Materiality (ADR-0003) ------------------------------------------------

def test_only_the_five_decision_categories_are_material(change_event):
    material = change_event[change_event["is_material"] == True]  # noqa: E712
    derived = change_event[change_event["is_material"] == False]  # noqa: E712
    assert set(material["change_category"]) <= set(T.MATERIAL_CATEGORIES)
    assert set(derived["change_category"]) <= set(T.DERIVED_CATEGORIES)
    assert set(derived["change_category"]) == {"premium", "agent"}


def test_a_premium_echo_is_carried_but_never_material(change_event):
    """One decision, two rows in one endorsement. If the premium move counted,
    every coverage increase would look like two decisions."""
    endorsement = rows_by(change_event, endorsement_id="END-00000001")
    assert len(endorsement) == 2
    assert set(endorsement["change_category"]) == {"coverage", "premium"}
    assert endorsement["is_material"].sum() == 1


# --- E2: change_direction --------------------------------------------------

def test_e2_categorical_direction_is_always_switch_never_null(change_event):
    categorical = change_event[
        change_event["change_category"].isin(T.CATEGORICAL_CATEGORIES)
    ]
    assert len(categorical) > 0
    assert (categorical["change_direction"] == "switch").all()
    assert categorical["change_direction"].notna().all()


def test_change_direction_is_never_null_anywhere(change_event):
    assert change_event["change_direction"].notna().all()
    assert set(change_event["change_direction"]) <= {"increase", "decrease", "switch"}


def test_numeric_direction_compares_values_not_strings(change_event):
    """``'300000' < '100000'`` is true lexically; this column is why "coverage
    increased" is a value filter rather than a string comparison."""
    assert row_by(change_event, change_event_id="CHG-00000101")["change_direction"] == "increase"
    assert row_by(change_event, change_event_id="CHG-00000601")["change_direction"] == "decrease"
    assert T.change_direction("coverage", 100000, 300000) == "increase"


def test_switch_is_never_used_for_a_numeric_category(change_event):
    numeric = change_event[change_event["change_category"].isin(T.NUMERIC_CATEGORIES)]
    assert len(numeric) > 0
    assert (numeric["change_direction"] != "switch").all()


# --- E1: change_pct --------------------------------------------------------

def test_e1_change_pct_is_null_for_every_categorical_change(change_event):
    categorical = change_event[
        change_event["change_category"].isin(T.CATEGORICAL_CATEGORIES)
    ]
    assert categorical["change_pct"].isna().all()


def test_e1_change_pct_is_null_when_the_old_value_is_zero(change_event):
    """Not infinity, not a sentinel — NULL (ADR-0003)."""
    row = row_by(change_event, change_event_id="CHG-00000403")
    assert row["old_value_num"] == 0.0
    assert pd.isna(row["change_pct"])
    assert row["change_direction"] == "increase"


def test_e1_change_pct_is_never_a_sentinel_or_infinite(change_event):
    values = change_event["change_pct"].dropna()
    assert len(values) > 0
    assert all(math.isfinite(float(v)) for v in values)


def test_change_pct_is_a_signed_percentage(change_event):
    assert row_by(change_event, change_event_id="CHG-00000405")["change_pct"] == 50.0
    assert row_by(change_event, change_event_id="CHG-00000601")["change_pct"] == -50.0


@pytest.mark.parametrize("old,new", [(0, 500), (None, 500)])
def test_change_pct_helper_returns_none_for_zero_or_null_old_value(old, new):
    assert T.change_pct("coverage", old, new) is None


# --- E3: typed value columns ----------------------------------------------

def test_e3_numeric_pair_is_null_exactly_for_categorical_categories(change_event):
    for _, row in change_event.iterrows():
        categorical = row["change_category"] in T.CATEGORICAL_CATEGORIES
        if categorical:
            assert pd.isna(row["old_value_num"]) and pd.isna(row["new_value_num"])
        else:
            assert pd.notna(row["new_value_num"])


def test_display_text_is_always_carried(change_event):
    assert change_event["old_value"].notna().all()
    assert change_event["new_value"].notna().all()


# --- E12: deductible rows exist only for COLL and COMP --------------------

def test_e12_deductible_rows_only_on_coll_and_comp(change_event):
    deductible = change_event[change_event["change_category"] == "deductible"]
    assert len(deductible) > 0
    assert set(deductible["coverage_line"]) <= set(T.DEDUCTIBLE_LINES)


def test_deductible_rows_are_never_derived_for_bi_pd_umuim():
    """The SCD2 fallback deriver must refuse to emit an invalid row (spec 01 §1)."""
    coverage = [
        {"policy_id": "P-91001", "coverage_line": "BI", "version_no": 1,
         "effective_from": D(400), "effective_to": D(100), "is_current": False,
         "limit_amount": 100000.0, "deductible_amount": 0.0, "endorsement_id": None},
        {"policy_id": "P-91001", "coverage_line": "BI", "version_no": 2,
         "effective_from": D(100), "effective_to": None, "is_current": True,
         "limit_amount": 100000.0, "deductible_amount": 500.0, "endorsement_id": None},
    ]
    derived = T.derive_change_events_from_scd2([], coverage)
    assert "deductible" not in set(derived["change_category"])


# --- Category proximity ----------------------------------------------------

def test_nearest_offset_is_negative_when_that_category_came_earlier(change_event):
    """P-10001's coverage increase sits 14 days after its address change."""
    row = row_by(change_event, change_event_id="CHG-00000101")
    assert row["nearest_address_change_offset_days"] == -14


def test_nearest_offset_is_positive_when_that_category_came_later(change_event):
    """From the address change, the nearest coverage change is 14 days ahead —
    the mirror of the previous test, so ``ABS(...) <= N`` is one symmetric
    filter with no ``OR``."""
    row = row_by(change_event, change_event_id="CHG-00000103")
    assert row["nearest_coverage_change_offset_days"] == 14


def test_same_category_offset_refers_to_the_previous_distinct_change(change_event):
    """The rule that makes repeat-changer questions work: on a coverage row the
    coverage offset points at the *previous* coverage change, never at itself and
    never forward."""
    second = row_by(change_event, change_event_id="CHG-00000104")
    assert second["nearest_coverage_change_offset_days"] == -31

    first = row_by(change_event, change_event_id="CHG-00000101")
    # The first coverage change on the policy has no previous one, even though a
    # later coverage change exists.
    assert pd.isna(first["nearest_coverage_change_offset_days"])


def test_nearest_offset_is_null_when_that_category_never_changed(change_event):
    """NULL, not zero and not a sentinel. P-10004 never changed address, so the
    address offset is unknown; it did change status, so that offset is a number."""
    row = row_by(change_event, change_event_id="CHG-00000401")
    assert pd.isna(row["nearest_address_change_offset_days"])
    assert pd.notna(row["nearest_status_change_offset_days"])
    assert row["nearest_status_change_offset_days"] == 50


def test_symmetric_co_occurrence_is_a_single_abs_filter(change_event):
    vehicle = row_by(change_event, change_event_id="CHG-00000801")
    address = row_by(change_event, change_event_id="CHG-00000802")
    assert vehicle["nearest_address_change_offset_days"] == 25
    assert address["nearest_vehicle_change_offset_days"] == -25
    assert abs(vehicle["nearest_address_change_offset_days"]) == abs(
        address["nearest_vehicle_change_offset_days"])


# --- Prior-window context --------------------------------------------------

def test_prior_windows_count_material_changes_strictly_before_the_change(change_event):
    """A change cannot precede itself, and co-committed siblings are one decision
    (ADR-0003) — so the premium echo reports the address change only."""
    coverage = row_by(change_event, change_event_id="CHG-00000101")
    premium = row_by(change_event, change_event_id="CHG-00000102")
    assert coverage["material_changes_prior_30d"] == 1  # the address change 14 days earlier
    assert premium["material_changes_prior_30d"] == 1   # not 2: the sibling is same-day


def test_prior_windows_widen_monotonically(change_event):
    assert (change_event["material_changes_prior_30d"]
            <= change_event["material_changes_prior_60d"]).all()
    assert (change_event["material_changes_prior_60d"]
            <= change_event["material_changes_prior_90d"]).all()


def test_prior_windows_on_the_cluster_policy(change_event):
    row = row_by(change_event, change_event_id="CHG-00000504")
    assert row["material_changes_prior_30d"] == 3
    assert row["material_changes_prior_90d"] == 3


# --- Denormalised policy context ------------------------------------------

def test_policy_start_date_and_state_are_denormalised(change_event):
    row = row_by(change_event, change_event_id="CHG-00000101")
    assert row["policy_start_date"] == D(900)
    # Read from the SCD2 version covering the change date, not the current one.
    assert row["policy_state"] == "CA"


def test_tenure_is_derived_never_stored(change_event):
    assert "tenure_days" not in change_event.columns
    assert "policy_age_days" not in change_event.columns
