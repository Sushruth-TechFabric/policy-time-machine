"""The SCD Type 2 fallback deriver.

Spec 01 §3 lists seven source tables and no change-event table, while §2 and §4
both treat change events as generator output. ``derive_change_events_from_scd2``
covers the reading where the generator emits only the SCD Type 2 history, so the
pipeline runs either way. Flagged as an ambiguity in ``transformations.py``.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd
import pytest

import transformations as T
from conftest import D

FAR_FUTURE = _dt.date(9999, 12, 31)


@pytest.fixture()
def scd2_sources():
    history = [
        {"policy_id": "P-70001", "version_no": 1, "customer_id": "C-700001",
         "effective_from": D(400), "effective_to": D(200), "is_current": False,
         "policy_status": "active", "agent_id": "AGT-0001",
         "garaging_city": "Austin", "garaging_state": "TX",
         "garaging_postal_code": "73301", "primary_vehicle_id": "VEH-000001",
         "term_start_date": D(400), "term_end_date": D(35),
         "annual_premium": 1200.0, "endorsement_id": None},
        # One relocation touching city, state and postal code together.
        {"policy_id": "P-70001", "version_no": 2, "customer_id": "C-700001",
         "effective_from": D(200), "effective_to": D(100), "is_current": False,
         "policy_status": "active", "agent_id": "AGT-0001",
         "garaging_city": "Dallas", "garaging_state": "CA",
         "garaging_postal_code": "75201", "primary_vehicle_id": "VEH-000001",
         "term_start_date": D(400), "term_end_date": D(35),
         "annual_premium": 1200.0, "endorsement_id": "END-70000002"},
        # A status change and a premium move committed together.
        {"policy_id": "P-70001", "version_no": 3, "customer_id": "C-700001",
         "effective_from": D(100), "effective_to": FAR_FUTURE, "is_current": True,
         "policy_status": "lapsed", "agent_id": "AGT-0001",
         "garaging_city": "Dallas", "garaging_state": "CA",
         "garaging_postal_code": "75201", "primary_vehicle_id": "VEH-000001",
         "term_start_date": D(400), "term_end_date": D(35),
         "annual_premium": 1330.0, "endorsement_id": "END-70000003"},
    ]
    coverage = [
        {"policy_id": "P-70001", "coverage_line": "COLL", "version_no": 1,
         "effective_from": D(400), "effective_to": D(150), "is_current": False,
         "limit_amount": 25000.0, "deductible_amount": 1000.0,
         "endorsement_id": None},
        # Limit up and deductible down in one version transition: two rows.
        {"policy_id": "P-70001", "coverage_line": "COLL", "version_no": 2,
         "effective_from": D(150), "effective_to": FAR_FUTURE, "is_current": True,
         "limit_amount": 50000.0, "deductible_amount": 500.0,
         "endorsement_id": "END-70000004"},
    ]
    return history, coverage


def test_one_row_per_category_per_version_transition(scd2_sources):
    """A relocation touching three columns is one address change, not three —
    otherwise "three material changes in 30 days" stops meaning anything
    (ADR-0003)."""
    history, coverage = scd2_sources
    derived = T.derive_change_events_from_scd2(history, coverage)
    address = derived[derived["change_category"] == "address"]
    assert len(address) == 1
    assert address.iloc[0]["change_date"] == D(200)
    assert address.iloc[0]["old_value"] == "Austin"
    assert address.iloc[0]["new_value"] == "Dallas"


def test_status_and_premium_are_emitted_separately(scd2_sources):
    history, coverage = scd2_sources
    derived = T.derive_change_events_from_scd2(history, coverage)
    at_100 = derived[derived["change_date"] == D(100)]
    assert set(at_100["change_category"]) == {"status", "premium"}
    assert set(at_100["endorsement_id"]) == {"END-70000003"}


def test_coverage_and_deductible_are_separate_categories(scd2_sources):
    history, coverage = scd2_sources
    derived = T.derive_change_events_from_scd2(history, coverage)
    at_150 = derived[derived["change_date"] == D(150)]
    assert set(at_150["change_category"]) == {"coverage", "deductible"}
    assert set(at_150["coverage_line"]) == {"COLL"}


def test_numeric_categories_carry_typed_values(scd2_sources):
    history, coverage = scd2_sources
    derived = T.derive_change_events_from_scd2(history, coverage)
    coverage_row = derived[derived["change_category"] == "coverage"].iloc[0]
    assert coverage_row["old_value_num"] == 25000.0
    assert coverage_row["new_value_num"] == 50000.0
    address_row = derived[derived["change_category"] == "address"].iloc[0]
    assert pd.isna(address_row["old_value_num"])
    assert pd.isna(address_row["new_value_num"])


def test_renewal_is_never_emitted_as_a_change_event():
    """Renewal is a Timeline Event, never a Policy Change, and renewal-driven
    status recalculations are never emitted (spec 01 §6 rule 2)."""
    history = [
        {"policy_id": "P-70002", "version_no": 1, "customer_id": "C-700002",
         "effective_from": D(400), "effective_to": D(35), "is_current": False,
         "policy_status": "active", "agent_id": "AGT-0001",
         "garaging_city": "Austin", "garaging_state": "TX",
         "garaging_postal_code": "73301", "primary_vehicle_id": "VEH-000001",
         "term_start_date": D(400), "term_end_date": D(35),
         "annual_premium": 1200.0, "endorsement_id": None},
        # Only the term moved: a renewal.
        {"policy_id": "P-70002", "version_no": 2, "customer_id": "C-700002",
         "effective_from": D(35), "effective_to": FAR_FUTURE, "is_current": True,
         "policy_status": "active", "agent_id": "AGT-0001",
         "garaging_city": "Austin", "garaging_state": "TX",
         "garaging_postal_code": "73301", "primary_vehicle_id": "VEH-000001",
         "term_start_date": D(35), "term_end_date": D(-330),
         "annual_premium": 1200.0, "endorsement_id": None},
    ]
    derived = T.derive_change_events_from_scd2(history, [])
    assert len(derived) == 0


def test_change_event_ids_follow_the_identifier_contract(scd2_sources):
    history, coverage = scd2_sources
    derived = T.derive_change_events_from_scd2(history, coverage)
    assert derived["change_event_id"].str.match(r"^CHG-\d{8}$").all()
    assert derived["change_event_id"].is_unique
    # E19: no derived identifier may look like a policy reference.
    assert not derived["change_event_id"].map(T.matches_policy_id_pattern).any()


def test_derivation_is_deterministic(scd2_sources):
    history, coverage = scd2_sources
    first = T.derive_change_events_from_scd2(history, coverage)
    second = T.derive_change_events_from_scd2(history, coverage)
    pd.testing.assert_frame_equal(first, second)


def test_derived_events_flow_through_the_whole_build(scd2_sources, anchor_date):
    """The fallback path must produce a curated layer that satisfies the same
    invariants as the generator-emitted path."""
    history, coverage = scd2_sources
    changes = T.derive_change_events_from_scd2(history, coverage)
    built = T.build_all(
        changes=changes, claims=[], policy_history=history,
        policy_coverage_history=coverage, claim_payment=[],
        anchor_date=anchor_date, k=5,
    )
    change_event = built["policy_change_event"]
    assert len(change_event) == len(changes)
    assert change_event["change_direction"].notna().all()
    # No claims, so every linkage column is NULL on every row (E4).
    for column in T.LINKAGE_COLUMNS:
        assert change_event[column].isna().all()
    assert built["policy_profile"].iloc[0]["material_change_count"] == 4
