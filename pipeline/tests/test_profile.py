"""``policy_profile`` — spec 02 §4, ADR-0006, expectation E20.

The corollary that governs this table: pre-compute event-to-event deltas, never
event-to-now deltas. Recency is expressed by storing *dates*.
"""

from __future__ import annotations

import datetime as _dt
import re

import pandas as pd

import transformations as T
from conftest import D, row_by


# --- E20: recency is dates only -------------------------------------------

def test_e20_recency_columns_are_dates_not_day_counts(policy_profile):
    """A day-count computed here would be anchored to ``anchor_date`` and would
    disagree with ``CURRENT_DATE`` arithmetic by exactly the staleness gap."""
    for column in ("last_material_change_date", "last_claim_date"):
        values = [v for v in policy_profile[column] if pd.notna(v)]
        assert values, f"{column} must be populated somewhere in the fixture"
        assert all(isinstance(v, _dt.date) for v in values)


def test_e20_no_column_stores_an_event_to_now_delta(policy_profile):
    """A schema review, per spec 02 §8. ``*_per_year`` are rates over tenure —
    they answer "how often", not "how long ago" — and are explicitly required
    rate-normalised by ADR-0010."""
    banned = re.compile(
        r"(days_since|days_ago|_age_days|days_to_today|days_from_now|recency_days"
        r"|days_since_last_claim|days_since_last_change)",
        re.IGNORECASE,
    )
    offenders = [c for c in policy_profile.columns if banned.search(c)]
    assert offenders == []


def test_recent_is_answerable_at_query_time_from_the_stored_dates(policy_profile, anchor_date):
    """"Recent" defaults to 90 days and is computed from the dates, not stored."""
    ninety_days_ago = anchor_date - _dt.timedelta(days=90)
    recent = policy_profile[
        policy_profile["last_material_change_date"].map(
            lambda d: pd.notna(d) and d >= ninety_days_ago
        )
    ]
    assert len(recent) > 0


# --- Grain and current state ----------------------------------------------

def test_one_row_per_policy_including_policies_with_no_changes(policy_profile, sources):
    expected = set(sources["policy_history"]["policy_id"])
    assert set(policy_profile["policy_id"]) == expected
    assert policy_profile["policy_id"].is_unique
    assert "P-10009" in set(policy_profile["policy_id"])  # a claim, never a change
    assert "P-10011" in set(policy_profile["policy_id"])


def test_current_state_reads_the_current_scd2_version(policy_profile):
    row = row_by(policy_profile, policy_id="P-10001")
    assert row["current_city"] == "Dallas"
    assert row["current_state"] == "CA"
    assert row["policy_start_date"] == D(900)
    assert row["current_coll_limit"] == 60000.0
    assert row["current_bi_limit"] == 100000.0
    assert row["current_coll_deductible"] == 500.0


# --- Behavioural summary ---------------------------------------------------

def test_material_change_count_excludes_derived_changes(policy_profile):
    """P-10001 has four change rows; the premium echo is not one of the three
    material ones (ADR-0003)."""
    row = row_by(policy_profile, policy_id="P-10001")
    assert row["material_change_count"] == 3
    assert row["coverage_change_count"] == 2
    assert row["address_change_count"] == 1


def test_category_counts_sum_to_the_material_count(policy_profile):
    columns = [f"{c}_change_count" for c in T.MATERIAL_CATEGORIES]
    assert (policy_profile[columns].sum(axis=1)
            == policy_profile["material_change_count"]).all()


def test_peak_material_changes_30d(policy_profile):
    assert row_by(policy_profile, policy_id="P-10005")["peak_material_changes_30d"] == 4
    assert row_by(policy_profile, policy_id="P-10003")["peak_material_changes_30d"] == 1
    assert row_by(policy_profile, policy_id="P-10009")["peak_material_changes_30d"] == 0


def test_peak_material_changes_30d_agrees_with_the_cluster_rule(policy_profile, pattern_match):
    """The profile's peak column and ADR-0009's ``rapid_change_cluster`` are two
    views of the same window scan."""
    clustered = set(pattern_match[
        pattern_match["pattern_code"] == "rapid_change_cluster"]["policy_id"])
    for _, row in policy_profile.iterrows():
        assert (row["peak_material_changes_30d"] >= T.PATTERN_CLUSTER_MIN_CHANGES) == (
            row["policy_id"] in clustered)


def test_rates_are_normalised_by_tenure_not_by_calendar(policy_profile, anchor_date):
    row = row_by(policy_profile, policy_id="P-10001")
    tenure_years = 900 / 365.25
    assert abs(float(row["material_changes_per_year"]) - 3 / tenure_years) < 1e-4
    assert abs(float(row["claims_per_year"]) - 1 / tenure_years) < 1e-4


def test_net_coverage_direction(policy_profile):
    assert row_by(policy_profile, policy_id="P-10001")["net_coverage_direction"] == "increase"
    assert row_by(policy_profile, policy_id="P-10009")["net_coverage_direction"] == "none"


def test_max_severity_band_is_ordinal_not_alphabetical(policy_profile):
    """Alphabetically "severe" sorts after "catastrophic"; by band it does not."""
    assert row_by(policy_profile, policy_id="P-10005")["max_severity_band"] == "catastrophic"
    assert row_by(policy_profile, policy_id="P-10001")["max_severity_band"] == "severe"
    assert pd.isna(row_by(policy_profile, policy_id="P-10003")["max_severity_band"])


def test_mean_limit_utilization_skips_null_utilisations(policy_profile):
    assert row_by(policy_profile, policy_id="P-10007")["mean_limit_utilization"] == 97.0
    # P-10011's only claim has a zero limit, so utilisation is unknown, not zero.
    assert pd.isna(row_by(policy_profile, policy_id="P-10011")["mean_limit_utilization"])


def test_share_material_changes_within_60d_before_loss(policy_profile):
    """P-10005: all four material changes fall inside 60 days before the loss."""
    assert row_by(policy_profile, policy_id="P-10005")[
        "share_material_changes_within_60d_before_loss"] == 1.0
    # P-10003 has changes but no claims: the share is zero, not NULL.
    assert row_by(policy_profile, policy_id="P-10003")[
        "share_material_changes_within_60d_before_loss"] == 0.0
    # P-10009 has no material changes at all: the share is undefined.
    assert pd.isna(row_by(policy_profile, policy_id="P-10009")[
        "share_material_changes_within_60d_before_loss"])


def test_claim_counts_match_the_claim_table(policy_profile, claim_event):
    counts = claim_event.groupby("policy_id")["claim_id"].nunique().to_dict()
    for _, row in policy_profile.iterrows():
        assert row["claim_count"] == counts.get(row["policy_id"], 0)


def test_last_claim_date_is_the_latest_loss_date(policy_profile):
    assert row_by(policy_profile, policy_id="P-10002")["last_claim_date"] == D(34)
    assert pd.isna(row_by(policy_profile, policy_id="P-10003")["last_claim_date"])


def test_profile_column_order_matches_the_declared_schema(policy_profile):
    assert list(policy_profile.columns) == [n for n, _ in T.POLICY_PROFILE_SCHEMA]
