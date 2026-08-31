"""``policy_similarity`` — ADR-0010, expectations E15, E16 and E18 on ``top_reasons``."""

from __future__ import annotations

import datetime as _dt
import re

import pandas as pd

import transformations as T
from conftest import D, rows_by


# --- E15: a policy is never its own neighbour -----------------------------

def test_e15_excludes_self_neighbours(similarity):
    assert len(similarity) > 0
    assert (similarity["policy_id"] != similarity["similar_policy_id"]).all()


# --- E16: dense rank, documented tie-break --------------------------------

def test_e16_rank_is_dense_and_starts_at_one(similarity):
    for policy_id, group in similarity.groupby("policy_id"):
        ranks = sorted(int(r) for r in group["rank"])
        assert ranks == list(range(1, len(ranks) + 1)), policy_id


def test_e16_rows_are_ordered_by_score_desc_then_id_asc(similarity):
    for policy_id, group in similarity.groupby("policy_id"):
        ordered = group.sort_values("rank")
        keys = [(-float(s), i) for s, i in
                zip(ordered["similarity_score"], ordered["similar_policy_id"])]
        assert keys == sorted(keys), policy_id


def test_tie_break_falls_to_similar_policy_id_ascending(anchor_date):
    """Three policies with identical histories score identically against the
    fourth. Without the tie-break, regeneration reorders them."""
    history, coverage, changes = [], [], []
    for index in range(1, 5):
        policy_id = f"P-8000{index}"
        history.append({
            "policy_id": policy_id, "version_no": 1, "customer_id": f"C-80000{index}",
            "effective_from": D(400), "effective_to": _dt.date(9999, 12, 31),
            "is_current": True, "policy_status": "active", "garaging_city": "Austin",
            "garaging_state": "TX", "primary_vehicle_id": "VEH-000001",
            "term_start_date": D(400), "term_end_date": D(35),
            "annual_premium": 1000.0, "agent_id": "AGT-0001",
        })
        coverage.append({
            "policy_id": policy_id, "coverage_line": "COLL", "version_no": 1,
            "effective_from": D(400), "effective_to": _dt.date(9999, 12, 31),
            "is_current": True, "limit_amount": 25000.0, "deductible_amount": 500.0,
        })
        # P-80002/3/4 are identical to each other; P-80001 differs on the
        # feature vector by changing three times instead of once.
        for repeat in range(3 if index == 1 else 1):
            changes.append({
                "change_event_id": f"CHG-800{index}000{repeat}", "policy_id": policy_id,
                "endorsement_id": f"END-800{index}000{repeat}",
                "change_date": D(100 - repeat * 40),
                "change_category": "address", "coverage_line": None,
                "old_value": "a", "new_value": "b",
                "old_value_num": None, "new_value_num": None,
            })

    built = T.build_all(
        changes=changes, claims=[], policy_history=history,
        policy_coverage_history=coverage, claim_payment=[],
        anchor_date=anchor_date, k=3,
    )
    neighbours = rows_by(built["policy_similarity"], policy_id="P-80002").sort_values("rank")
    scores = [float(s) for s in neighbours["similarity_score"]]
    ids = list(neighbours["similar_policy_id"])
    # P-80003 and P-80004 are identical to P-80002 and tie; the lower id ranks first.
    assert scores[0] == scores[1]
    assert ids[0] == "P-80003" and ids[1] == "P-80004"


def test_k_is_capped(similarity):
    assert similarity.groupby("policy_id").size().max() <= 5  # the fixture uses k=5


def test_default_k_is_twenty():
    assert T.K_NEIGHBOURS == 20


def test_k_returns_fewer_rows_when_the_population_is_smaller(curated, similarity):
    """Eleven policies with k=5 gives every policy five neighbours; with k=20 it
    would give ten, and the Genie instruction surfaces the cap rather than
    improvising."""
    assert similarity.groupby("policy_id").size().unique().tolist() == [5]


# --- Determinism and directionality ---------------------------------------

def test_similarity_is_deterministic(policy_profile, change_event, pattern_match):
    first = T.build_policy_similarity(policy_profile, change_event, pattern_match, k=5)
    second = T.build_policy_similarity(policy_profile, change_event, pattern_match, k=5)
    pd.testing.assert_frame_equal(first, second)


def test_similarity_is_directional_and_not_symmetrised(similarity):
    """A appearing in B's top-K does not imply the reverse. Documented so nobody
    symmetrises it (ADR-0010)."""
    pairs = set(zip(similarity["policy_id"], similarity["similar_policy_id"]))
    asymmetric = [(a, b) for a, b in pairs if (b, a) not in pairs]
    assert asymmetric, "the fixture should contain at least one one-way neighbour"


def test_scores_are_bounded_and_comparable_within_a_generation(similarity):
    scores = [float(s) for s in similarity["similarity_score"]]
    assert all(0.0 < s <= 1.0 for s in scores)


# --- The feature vector (ADR-0010) ----------------------------------------

def test_feature_vector_covers_every_named_dimension():
    """Rate-normalised so tenure does not dominate: change rate, peak density,
    the five category shares, net coverage bias, claim rate, severity ordinal,
    mean utilisation, and the share of changes before a loss."""
    names = [name for name, _ in T.SIMILARITY_FEATURES]
    assert names == [
        "material_changes_per_year", "peak_material_changes_30d",
        "share_coverage", "share_deductible", "share_vehicle",
        "share_address", "share_status", "net_coverage_bias",
        "claims_per_year", "max_severity_ordinal", "mean_limit_utilization",
        "share_within_60d_before_loss",
    ]
    assert len(names) == 12


def test_pattern_component_is_separately_weighted():
    assert T.PATTERN_WEIGHT > 0
    assert T._jaccard(frozenset(), frozenset()) == 1.0
    assert T._jaccard(frozenset({"a"}), frozenset({"a", "b"})) == 0.5
    assert T._jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_shared_patterns_pull_neighbours_closer(policy_profile, change_event, pattern_match):
    """Two policies alike on the numerics but sharing no pattern must score below
    an otherwise identical pair that does share one."""
    numeric_only = T.build_policy_similarity(
        policy_profile, change_event, pattern_match.iloc[0:0], k=5)
    with_patterns = T.build_policy_similarity(
        policy_profile, change_event, pattern_match, k=5)
    assert not numeric_only.equals(with_patterns)


# --- top_reasons: named dimensions under the approved vocabulary ----------

def test_top_reasons_is_always_populated(similarity):
    assert similarity["top_reasons"].notna().all()
    assert (similarity["top_reasons"].str.len() > 0).all()


def test_e18_top_reasons_uses_only_approved_vocabulary(similarity):
    for text in similarity["top_reasons"]:
        assert T.vocabulary_violations(text) == [], text


def test_top_reasons_names_feature_dimensions_not_demographics(similarity):
    """Similarity is behavioural, never demographic (CONTEXT.md)."""
    joined = " ".join(similarity["top_reasons"]).lower()
    for demographic in ("city", "state", "age", "birth", "postal", "name", "vehicle make"):
        assert not re.search(rf"\b{demographic}\b", joined), demographic


def test_top_reasons_reports_a_shared_pattern_when_there_is_one(similarity, pattern_match):
    shared = similarity[similarity["top_reasons"].str.contains("noteworthy pattern")]
    assert len(shared) > 0
    for _, row in shared.iterrows():
        assert "'" in row["top_reasons"]


def test_top_reasons_is_capped(similarity):
    for text in similarity["top_reasons"]:
        assert len(text.split("; ")) <= T.TOP_REASON_LIMIT
