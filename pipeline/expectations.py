"""The expectations catalogue of `docs/specs/02-semantic-layer.md` §8, as SQL.

Separated from ``dlt_pipeline.py`` so it imports without PySpark or ``dlt`` and
the test suite can assert on it directly: that every numbered expectation is
present, and that the two regex-driven ones (E18's banned vocabulary, E19's
identifier reservation) agree with the Python predicates in ``transformations.py``
that the unit tests exercise. A rule enforced in two places that disagree is the
failure mode ADR-0009 names by hand.

Every invariant is enforced with ``expect_all_or_fail`` (ADR-0013): a violation
fails the run rather than quarantining rows. These rules are the product's
correctness, not a data quality score.

Coverage map:

* **E1–E12, E17, E19** — row predicates on one table; attached to that table.
* **E8, E13, E14, E16** — cross-table or cross-row; enforced by the ``qa_*``
  assertion tables in ``dlt_pipeline.py``, which materialise a join or a window
  and fail on any violating row. (E8 also has a same-table form here, checking
  that ``next_claim_severity`` uses the documented cuts.)
* **E18** — attached to every table carrying a user-facing string.
* **E20** — a property of the schema, not of a row; enforced by review against
  the specification. The review is written out in ``dlt_pipeline``'s docstring
  and executed as a column-name check in ``tests/test_profile.py``.
"""

from __future__ import annotations

import datetime as _dt

import transformations as T

#: E19: the pattern the app uses to detect policy references (ADR-0007). The
#: doubled backslashes survive Spark SQL string-literal unescaping to reach
#: RLIKE as ``\b``.
POLICY_ID_RLIKE = r"(?i)\\bP-[0-9]{5}\\b"

#: E18: built from the one authored banned-term list, so the SQL guard and
#: :func:`transformations.vocabulary_violations` can never drift.
BANNED_RLIKE = (
    r"(?i)\\b(" + "|".join(term.replace(" ", r"\\s+") for term in T.BANNED_VOCABULARY)
    + r")\\b"
)


def _in_list(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


_CATEGORICAL = _in_list(T.CATEGORICAL_CATEGORIES)
_MATERIAL = _in_list(T.MATERIAL_CATEGORIES)
_DEDUCTIBLE_LINES = _in_list(T.DEDUCTIBLE_LINES)

#: The severity cuts as SQL, mirroring :func:`transformations.severity_band`.
#: Written once and reused by E8 and E9 so the two cannot disagree (ADR-0008).
SEVERITY_CASE = (
    "CASE WHEN {amount} < 2500 THEN 'minor' "
    "WHEN {amount} < 10000 THEN 'moderate' "
    "WHEN {amount} < 50000 THEN 'severe' ELSE 'catastrophic' END"
)

_LINKED = " AND ".join(f"{c} IS NOT NULL" for c in T.LINKAGE_COLUMNS)
_UNLINKED = " AND ".join(f"{c} IS NULL" for c in T.LINKAGE_COLUMNS)


def policy_change_event(anchor_sql: str) -> dict[str, str]:
    return {
        # E1 — never a sentinel, never infinity; NULL instead (ADR-0003)
        "E1_change_pct_is_never_a_sentinel_or_infinite":
            "change_pct IS NULL OR (NOT isnan(change_pct) "
            "AND change_pct != double('Infinity') "
            "AND change_pct != double('-Infinity'))",
        "E1_change_pct_is_null_for_categoricals":
            f"change_category NOT IN {_CATEGORICAL} OR change_pct IS NULL",
        "E1_change_pct_is_null_when_the_old_value_is_zero_or_null":
            "NOT (old_value_num IS NULL OR old_value_num = 0) OR change_pct IS NULL",
        # E2 — 'switch' for every categorical change, never NULL
        "E2_change_direction_is_never_null":
            "change_direction IN ('increase', 'decrease', 'switch')",
        "E2_categorical_change_direction_is_switch":
            f"change_category NOT IN {_CATEGORICAL} OR change_direction = 'switch'",
        "E2_numeric_change_direction_is_never_switch":
            f"change_category IN {_CATEGORICAL} OR change_direction != 'switch'",
        # E3 — the numeric pair is NULL exactly for categorical categories
        "E3_numeric_pair_is_null_exactly_for_categoricals":
            f"CASE WHEN change_category IN {_CATEGORICAL} "
            "THEN old_value_num IS NULL AND new_value_num IS NULL "
            "ELSE new_value_num IS NOT NULL END",
        # E4 — all seven linkage columns NULL together or populated together
        "E4_linkage_columns_null_together_or_populated_together":
            f"({_LINKED}) OR ({_UNLINKED})",
        # E5 — change_timing is exactly one of two values on every linked row
        "E5_change_timing_domain_on_linked_rows":
            "next_claim_id IS NULL OR "
            "change_timing IN ('before_loss', 'after_loss_before_report')",
        # E6 — days_to_next_claim_report >= 0 always
        "E6_report_delta_is_never_negative":
            "days_to_next_claim_report IS NULL OR days_to_next_claim_report >= 0",
        # E7 — the sign of the loss delta agrees with change_timing
        "E7_loss_delta_sign_agrees_with_change_timing":
            "next_claim_id IS NULL "
            "OR (change_timing = 'before_loss' AND days_to_next_claim_loss >= 0) "
            "OR (change_timing = 'after_loss_before_report' "
            "AND days_to_next_claim_loss < 0)",
        # E8 — same cuts as claim_event.severity_band; agreement with the actual
        #      claim row is checked by qa_severity_agreement
        "E8_next_claim_severity_uses_the_documented_cuts":
            "next_claim_id IS NULL OR next_claim_severity = "
            + SEVERITY_CASE.format(amount="next_claim_amount"),
        # E12 — deductible rows exist only for COLL and COMP (ADR-0005)
        "E12_deductible_rows_only_on_coll_and_comp":
            f"change_category != 'deductible' "
            f"OR coverage_line IN {_DEDUCTIBLE_LINES}",
        # E17 — no event date exceeds anchor_date (ADR-0006)
        "E17_change_date_does_not_exceed_the_anchor":
            f"change_date <= {anchor_sql}",
        # E19 — the identifier lexical reservation (ADR-0007)
        "E19_identifiers_do_not_look_like_policy_ids":
            f"NOT (change_event_id RLIKE '{POLICY_ID_RLIKE}' "
            f"OR coalesce(endorsement_id, '') RLIKE '{POLICY_ID_RLIKE}' "
            f"OR coalesce(customer_id, '') RLIKE '{POLICY_ID_RLIKE}' "
            f"OR coalesce(next_claim_id, '') RLIKE '{POLICY_ID_RLIKE}')",
        "E19_policy_id_matches_the_policy_pattern":
            f"policy_id RLIKE '{POLICY_ID_RLIKE}'",
        # Grain and materiality (ADR-0003)
        "change_event_id_is_present": "change_event_id IS NOT NULL",
        "is_material_matches_the_five_decision_categories":
            f"is_material = (change_category IN {_MATERIAL})",
    }


def claim_event(anchor_sql: str) -> dict[str, str]:
    return {
        # E9 — the bands partition the amount range with no overlap and no gap
        "E9_severity_band_partitions_the_amount_range":
            "settled_amount >= 0 AND severity_band = "
            + SEVERITY_CASE.format(amount="settled_amount"),
        # E10 — NULL when the limit is NULL or zero; never clamped above 100
        "E10_utilization_is_null_exactly_when_the_limit_is_null_or_zero":
            "(applicable_limit IS NULL OR applicable_limit = 0) "
            "= (limit_utilization_pct IS NULL)",
        "E10_utilization_is_never_clamped":
            "limit_utilization_pct IS NULL OR abs(limit_utilization_pct "
            "- (settled_amount / applicable_limit * 100)) < 1e-6",
        "E10_at_or_near_limit_uses_the_named_constant":
            "limit_utilization_pct IS NULL OR at_or_near_limit = "
            f"(limit_utilization_pct >= {T.AT_OR_NEAR_LIMIT_PCT})",
        # E11 — report_date >= loss_date (ADR-0004)
        "E11_report_date_is_at_or_after_the_loss_date": "report_date >= loss_date",
        "E11_loss_to_report_days_matches_the_dates":
            "loss_to_report_days = datediff(report_date, loss_date)",
        # E17
        "E17_claim_dates_do_not_exceed_the_anchor":
            f"loss_date <= {anchor_sql} AND report_date <= {anchor_sql}",
        # E19
        "E19_identifiers_do_not_look_like_policy_ids":
            f"NOT (claim_id RLIKE '{POLICY_ID_RLIKE}' "
            f"OR coalesce(customer_id, '') RLIKE '{POLICY_ID_RLIKE}')",
        "E19_policy_id_matches_the_policy_pattern":
            f"policy_id RLIKE '{POLICY_ID_RLIKE}'",
        "prior_windows_widen_monotonically":
            "material_changes_prior_30d <= material_changes_prior_60d "
            "AND material_changes_prior_60d <= material_changes_prior_90d",
        "gap_count_is_never_negative": "material_changes_in_loss_report_gap >= 0",
        "settled_amount_is_present": "settled_amount IS NOT NULL",
    }


def policy_profile(anchor_sql: str) -> dict[str, str]:
    return {
        # E20 is a schema review (see the module docstring). Its row-level
        # consequence — recency columns hold dates, not day counts — is checked.
        "E20_recency_is_a_date_at_or_before_the_anchor":
            f"(last_material_change_date IS NULL "
            f"OR last_material_change_date <= {anchor_sql})",
        "E17_last_claim_date_does_not_exceed_the_anchor":
            f"(last_claim_date IS NULL OR last_claim_date <= {anchor_sql})",
        "E19_identifiers_do_not_look_like_policy_ids":
            f"NOT (coalesce(customer_id, '') RLIKE '{POLICY_ID_RLIKE}' "
            f"OR coalesce(current_primary_vehicle, '') RLIKE '{POLICY_ID_RLIKE}')",
        "E19_policy_id_matches_the_policy_pattern":
            f"policy_id RLIKE '{POLICY_ID_RLIKE}'",
        "category_counts_sum_to_the_material_count":
            "coverage_change_count + deductible_change_count "
            "+ vehicle_change_count + address_change_count + status_change_count "
            "= material_change_count",
        # A same-table shadow of E13; the authoritative join is qa_pattern_consistency.
        "E13_noteworthy_pattern_count_equals_the_flags_that_are_true":
            "noteworthy_pattern_count = "
            + " + ".join(f"CAST({c} AS INT)" for c in T.PATTERN_FLAG_COLUMNS),
        "max_severity_band_domain":
            "max_severity_band IS NULL OR max_severity_band IN "
            + _in_list(T.SEVERITY_ORDER),
        "net_coverage_direction_domain":
            "net_coverage_direction IN ('increase', 'decrease', 'net_zero', 'none')",
        "share_is_a_fraction":
            "share_material_changes_within_60d_before_loss IS NULL "
            "OR share_material_changes_within_60d_before_loss BETWEEN 0 AND 1",
    }


def policy_timeline_event(anchor_sql: str) -> dict[str, str]:
    return {
        "E17_event_date_does_not_exceed_the_anchor": f"event_date <= {anchor_sql}",
        # E18 — the no-fraud-labelling boundary as a data-quality constraint
        "E18_display_label_uses_only_approved_vocabulary":
            f"NOT (display_label RLIKE '{BANNED_RLIKE}')",
        "E19_timeline_event_id_does_not_look_like_a_policy_id":
            f"NOT (timeline_event_id RLIKE '{POLICY_ID_RLIKE}')",
        # A policy_created row's source_id *is* a policy id, which E19 permits.
        "E19_source_id_is_a_policy_id_only_on_policy_created_rows":
            f"NOT (coalesce(source_id, '') RLIKE '{POLICY_ID_RLIKE}') "
            "OR event_type = 'policy_created'",
        "event_type_domain": f"event_type IN {_in_list(T.TIMELINE_EVENT_TYPES)}",
        "display_label_is_pre_rendered": "display_label IS NOT NULL",
        "amount_is_a_claim_or_payment_amount":
            "amount IS NULL OR event_type IN ('claim_filed', 'claim_payment')",
    }


def policy_pattern_match(anchor_sql: str) -> dict[str, str]:
    return {
        "E17_matched_on_date_does_not_exceed_the_anchor":
            f"matched_on_date <= {anchor_sql}",
        # E18 — these strings surface verbatim in Genie answers and in the UI
        "E18_pattern_name_uses_only_approved_vocabulary":
            f"NOT (pattern_name RLIKE '{BANNED_RLIKE}')",
        "E18_evidence_summary_uses_only_approved_vocabulary":
            f"NOT (evidence_summary RLIKE '{BANNED_RLIKE}')",
        "E19_evidence_identifiers_do_not_look_like_policy_ids":
            f"NOT (coalesce(evidence_change_event_id, '') RLIKE '{POLICY_ID_RLIKE}' "
            f"OR coalesce(evidence_claim_id, '') RLIKE '{POLICY_ID_RLIKE}')",
        "E19_policy_id_matches_the_policy_pattern":
            f"policy_id RLIKE '{POLICY_ID_RLIKE}'",
        "pattern_code_domain": f"pattern_code IN {_in_list(T.PATTERN_CODES)}",
        "every_match_carries_evidence":
            "evidence_change_event_id IS NOT NULL OR evidence_claim_id IS NOT NULL",
        "matched_on_date_is_present": "matched_on_date IS NOT NULL",
    }


def policy_similarity(k: int) -> dict[str, str]:
    return {
        # E15 — a policy is never its own neighbour
        "E15_excludes_self_neighbours": "policy_id != similar_policy_id",
        # E16 — within the cap here; density and ordering in qa_similarity_rank_density
        "E16_rank_is_within_the_documented_cap": f"`rank` BETWEEN 1 AND {k}",
        # E18 — top_reasons surfaces verbatim in the UI and in Genie's answers
        "E18_top_reasons_uses_only_approved_vocabulary":
            f"top_reasons IS NOT NULL AND NOT (top_reasons RLIKE '{BANNED_RLIKE}')",
        "E19_policy_ids_match_the_policy_pattern":
            f"policy_id RLIKE '{POLICY_ID_RLIKE}' "
            f"AND similar_policy_id RLIKE '{POLICY_ID_RLIKE}'",
        "similarity_score_is_present": "similarity_score IS NOT NULL",
    }


# --- Cross-table assertion tables ------------------------------------------

QA_SEVERITY_AGREEMENT = {
    # E8 — next_claim_severity equals severity_band for the same claim_id
    "E8_change_side_and_claim_side_severity_agree":
        "next_claim_severity = severity_band",
    "E8_change_side_and_claim_side_amount_agree":
        "next_claim_amount = settled_amount",
    "E8_change_side_and_claim_side_line_agree":
        "next_claim_coverage_line = coverage_line",
}

QA_PATTERN_CONSISTENCY = {
    # E13 — noteworthy_pattern_count equals COUNT(DISTINCT pattern_code)
    "E13_noteworthy_pattern_count_equals_distinct_pattern_codes":
        "noteworthy_pattern_count = matched_codes",
    # E14 — each boolean is true iff a matching row exists
    **{
        f"E14_flag_matches_a_row_for_{code}": f"pattern_{code} = (matched_{code} > 0)"
        for code in T.PATTERN_CODES
    },
}

QA_SIMILARITY_RANK_DENSITY = {
    # E16 — dense 1..K, ordered by similarity_score DESC then similar_policy_id ASC
    "E16_rank_is_dense_and_ordered_by_the_documented_tie_break":
        "`rank` = expected_rank",
}


def all_expectations(anchor_date: _dt.date, k: int = T.K_NEIGHBOURS) -> dict[str, dict[str, str]]:
    """Every catalogue, keyed by dataset name. Used by the pipeline and the tests."""
    anchor_sql = f"DATE'{anchor_date.isoformat()}'"
    return {
        "policy_change_event": policy_change_event(anchor_sql),
        "claim_event": claim_event(anchor_sql),
        "policy_profile": policy_profile(anchor_sql),
        "policy_timeline_event": policy_timeline_event(anchor_sql),
        "policy_pattern_match": policy_pattern_match(anchor_sql),
        "policy_similarity": policy_similarity(k),
        "qa_severity_agreement": QA_SEVERITY_AGREEMENT,
        "qa_pattern_consistency": QA_PATTERN_CONSISTENCY,
        "qa_similarity_rank_density": QA_SIMILARITY_RANK_DENSITY,
    }
