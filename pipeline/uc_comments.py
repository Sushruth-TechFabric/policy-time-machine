"""Unity Catalog table and column comments — the single authored source.

Genie reads table and column comments as context, so **comments are
semantic-layer content, not documentation** (ADR-0013). They are authored here,
versioned with `docs/specs/02-semantic-layer.md`, and reviewed like the Genie
instruction set. Comments and Genie instructions render from this one source and
must never be able to disagree — the P4 Genie instruction build imports
:data:`COMMENTS` rather than restating any of it.

Run ``python uc_comments.py`` to print the DDL script.

The five definitions spec 02 §9 requires **verbatim** are held in
:data:`VERBATIM` and asserted into their comments at import time, so an edit that
drifts from the specification fails immediately rather than at demo time. Only
markdown emphasis markers (``**``) are dropped; backticks are kept, since they
identify column names inside the sentence.
"""

from __future__ import annotations

import sys
from typing import Iterator

from transformations import SCHEMAS, vocabulary_violations

DEFAULT_CATALOG = "workspace"
DEFAULT_SCHEMA = "ptm_gold"

#: Quoted verbatim from spec 02 §9. Keyed by ``(table, column)``; ``None`` as the
#: column means the table comment.
VERBATIM: dict[tuple[str, str | None], str] = {
    ("policy_change_event", "next_claim_id"): (
        "The first claim on this policy reported at or after this change. "
        "Not the next claim by loss date. Many changes may share one claim."
    ),
    ("policy_change_event", "days_to_next_claim_loss"): (
        "Signed. Positive: the change preceded the loss. Negative: the change "
        "fell between the loss and its report. Filter with `change_timing`, not "
        "with the sign."
    ),
    ("policy_change_event", "change_timing"): (
        "Deliberately redundant with the sign of `days_to_next_claim_loss`. "
        "Use this rather than interpreting the sign."
    ),
    ("claim_event", "severity_band"): (
        "High-severity means `severe` or `catastrophic`."
    ),
    ("policy_timeline_event", None): (
        "For reading one policy's history. Do not aggregate; this table mixes grains."
    ),
}


def _v(table: str, column: str | None) -> str:
    return VERBATIM[(table, column)]


COMMENTS: dict[str, dict[str | None, str]] = {
    # -----------------------------------------------------------------------
    "policy_change_event": {
        None: (
            "One row per field change on a policy, material or otherwise. "
            "Grain: change event. Every change is linked forward to the first "
            "claim reported at or after it, so lookahead questions are flat "
            "filters. next_claim_id is many-to-one by design: use "
            "COUNT(DISTINCT next_claim_id) for any claim-level aggregate."
        ),
        "change_event_id": "Unique id of this change event.",
        "policy_id": "The policy this change was made to.",
        "customer_id": "The customer holding the policy.",
        "endorsement_id": (
            "Groups changes committed together in one transaction. A column, "
            "never a grain. Use COUNT(DISTINCT endorsement_id) to answer "
            "'how many customer interactions', not 'how many changes'."
        ),
        "change_date": "The date the new value took effect.",
        "change_category": (
            "One of coverage, deductible, vehicle, address, status, premium, agent. "
            "The first five are material; premium and agent changes are derived "
            "and never counted as material."
        ),
        "is_material": (
            "True only for the five decision categories: coverage, deductible, "
            "vehicle, address, status. A premium move that follows a coverage "
            "change is derived and is false here, so one decision never counts twice."
        ),
        "coverage_line": (
            "The coverage line this change touched: BI, PD, COLL, COMP or UMUIM. "
            "NULL for categories that are not line-specific."
        ),
        "old_value": "The previous value as display text.",
        "new_value": "The new value as display text.",
        "old_value_num": "The previous value as a number. NULL for categorical categories.",
        "new_value_num": "The new value as a number. NULL for categorical categories.",
        "change_direction": (
            "One of increase, decrease or switch. Always switch for a categorical "
            "change and never NULL. Use this rather than comparing old_value to "
            "new_value as text: '300000' < '100000' is true lexically."
        ),
        "change_pct": (
            "Signed percentage change from old_value_num to new_value_num. NULL "
            "for categorical categories and when the old value is zero or NULL. "
            "Never a sentinel and never infinity."
        ),
        "next_claim_id": _v("policy_change_event", "next_claim_id"),
        "days_to_next_claim_loss": _v("policy_change_event", "days_to_next_claim_loss"),
        "days_to_next_claim_report": (
            "Days from this change to the linked claim's report date. Always >= 0. "
            "NULL when there is no linked claim."
        ),
        "change_timing": _v("policy_change_event", "change_timing"),
        "next_claim_amount": "Settled amount of the linked claim.",
        "next_claim_severity": (
            "Severity band of the linked claim. High-severity means `severe` or "
            "`catastrophic`."
        ),
        "next_claim_coverage_line": "Coverage line the linked claim was filed against.",
        "change_relates_to_claimed_coverage": (
            "True when this change is on the same coverage line the linked claim "
            "was later filed against. Distinguishes a finding from a coincidence."
        ),
        "nearest_coverage_change_offset_days": (
            "Signed days to the nearest coverage change on this policy: negative "
            "if it came before this row, positive if after. On a coverage row it "
            "refers to the previous coverage change. Symmetric co-occurrence is "
            "ABS(...) <= N."
        ),
        "nearest_deductible_change_offset_days": (
            "Signed days to the nearest deductible change on this policy. See "
            "nearest_coverage_change_offset_days."
        ),
        "nearest_vehicle_change_offset_days": (
            "Signed days to the nearest vehicle change on this policy. See "
            "nearest_coverage_change_offset_days."
        ),
        "nearest_address_change_offset_days": (
            "Signed days to the nearest address change on this policy. See "
            "nearest_coverage_change_offset_days."
        ),
        "nearest_status_change_offset_days": (
            "Signed days to the nearest status change on this policy. See "
            "nearest_coverage_change_offset_days."
        ),
        "material_changes_prior_30d": (
            "Material changes on this policy in the 30 days before change_date, "
            "excluding this change and any committed alongside it."
        ),
        "material_changes_prior_60d": "As material_changes_prior_30d, over 60 days.",
        "material_changes_prior_90d": "As material_changes_prior_30d, over 90 days.",
        "policy_start_date": (
            "The policy's start date, denormalised. Tenure is derived at query "
            "time and never stored."
        ),
        "policy_state": "Garaging state at the time of the change.",
    },
    # -----------------------------------------------------------------------
    "claim_event": {
        None: (
            "One row per claim. This is the table for claim-level counting. "
            "All prior-change context columns are anchored on loss_date."
        ),
        "claim_id": "Unique id of the claim.",
        "policy_id": "The policy the claim was filed against.",
        "customer_id": "The customer holding the policy.",
        "coverage_line": (
            "The single coverage line the claim was filed against: BI, PD, COLL, "
            "COMP or UMUIM."
        ),
        "loss_date": "When the loss actually occurred.",
        "report_date": (
            "When the loss was reported to the insurer. Always at or after "
            "loss_date. The gap between the two is itself analytically interesting."
        ),
        "loss_to_report_days": (
            "Days from loss_date to report_date, the Loss-to-Report Gap. "
            "Always >= 0."
        ),
        "settled_amount": "The single settled amount for the claim.",
        "severity_band": _v("claim_event", "severity_band") + (
            " Bands are fixed dollar cuts: minor [0, 2500), moderate [2500, 10000), "
            "severe [10000, 50000), catastrophic [50000, and above)."
        ),
        "applicable_limit": "The limit on this coverage line at the loss date.",
        "limit_utilization_pct": (
            "settled_amount as a percentage of applicable_limit. NULL when the "
            "limit is NULL or zero. Values above 100 are legitimate and are never "
            "clamped. A separate axis from severity_band: a modest claim can "
            "exhaust a modest limit."
        ),
        "at_or_near_limit": (
            "True when limit_utilization_pct is 90 or above. NULL when "
            "utilisation is unknown."
        ),
        "claim_status": "Status of the claim.",
        "material_changes_prior_30d": (
            "Material changes on the policy in the 30 days up to and including "
            "loss_date."
        ),
        "material_changes_prior_60d": "As material_changes_prior_30d, over 60 days.",
        "material_changes_prior_90d": "As material_changes_prior_30d, over 90 days.",
        "material_changes_in_loss_report_gap": (
            "Material changes made after the loss occurred but at or before it "
            "was reported. Lets gap questions be answered at claim grain."
        ),
        "days_since_last_material_change_before_loss": (
            "Days from the most recent material change at or before the loss to "
            "the loss itself. An event-to-event delta, not a delta against today."
        ),
        "last_material_change_category": (
            "Category of the most recent material change at or before the loss."
        ),
        "last_material_change_date": (
            "Date of the most recent material change at or before the loss."
        ),
        "relevant_coverage_change_prior_60d": (
            "True when a coverage or deductible change on the same coverage line "
            "this claim was filed against occurred within 60 days before the loss."
        ),
    },
    # -----------------------------------------------------------------------
    "policy_profile": {
        None: (
            "One row per policy: current state, a behavioural summary, recency "
            "dates and the noteworthy pattern flags. Join here for policy detail. "
            "Recency is stored as dates; compute 'recent' at query time, "
            "defaulting to 90 days."
        ),
        "policy_id": "Unique id of the policy.",
        "customer_id": "The customer holding the policy.",
        "policy_status": "Current status: active, lapsed, reinstated, cancelled or non_renewed.",
        "policy_start_date": "When the policy began.",
        "term_start_date": "Start of the current term.",
        "term_end_date": "End of the current term. May legitimately be in the future.",
        "current_city": "Current garaging city.",
        "current_state": "Current garaging state.",
        "current_annual_premium": "Current annual premium.",
        "current_primary_vehicle": "Current primary vehicle id.",
        "current_coll_limit": "Current collision limit.",
        "current_comp_limit": "Current comprehensive limit.",
        "current_bi_limit": "Current bodily injury liability limit.",
        "current_coll_deductible": "Current collision deductible.",
        "current_comp_deductible": "Current comprehensive deductible.",
        "material_change_count": (
            "Total material changes over the policy's life. Excludes premium and "
            "agent changes."
        ),
        "material_changes_per_year": (
            "material_change_count normalised by tenure, so long-held policies do "
            "not look busier than they are."
        ),
        "peak_material_changes_30d": (
            "The largest number of material changes falling inside any 30-day span."
        ),
        "coverage_change_count": "Material coverage changes.",
        "deductible_change_count": "Material deductible changes.",
        "vehicle_change_count": "Material vehicle changes.",
        "address_change_count": "Material address changes.",
        "status_change_count": "Material status changes.",
        "net_coverage_direction": (
            "One of increase, decrease, net_zero or none, comparing coverage "
            "increases against coverage decreases over the policy's life."
        ),
        "claim_count": "Claims filed against the policy.",
        "claims_per_year": "claim_count normalised by tenure.",
        "max_severity_band": (
            "Highest severity band across the policy's claims, by band order not "
            "alphabetically. NULL when there are no claims."
        ),
        "mean_limit_utilization": (
            "Mean limit_utilization_pct across claims where utilisation is known."
        ),
        "share_material_changes_within_60d_before_loss": (
            "Share of this policy's material changes that fall within 60 days "
            "before one of its losses. NULL when the policy has no material changes."
        ),
        "last_material_change_date": (
            "Date of the most recent material change. Stored as a date, never as "
            "a day count: compute recency at query time from CURRENT_DATE."
        ),
        "last_claim_date": (
            "Loss date of the most recent claim. Stored as a date, never as a day "
            "count: compute recency at query time from CURRENT_DATE."
        ),
        "noteworthy_pattern_count": (
            "How many distinct noteworthy patterns this policy matches. "
            "Policies with nothing noteworthy are noteworthy_pattern_count = 0."
        ),
        "pattern_coverage_raised_then_claimed_same_line": (
            "True when a coverage increase was followed within 60 days by a claim "
            "on the same coverage line, before the loss."
        ),
        "pattern_deductible_lowered_before_claim": (
            "True when a deductible decrease was followed within 60 days by a "
            "claim, before the loss."
        ),
        "pattern_change_in_loss_report_gap": (
            "True when a material change occurred after a loss and before it was "
            "reported."
        ),
        "pattern_rapid_change_cluster": (
            "True when three or more material changes fall inside any 30-day span."
        ),
        "pattern_vehicle_and_address_within_60d": (
            "True when a vehicle change and an address change occurred within 60 "
            "days of each other."
        ),
        "pattern_claim_near_new_limit": (
            "True when a claim at or near the limit followed a rise in that "
            "line's limit within the prior 90 days."
        ),
    },
    # -----------------------------------------------------------------------
    "policy_timeline_event": {
        None: _v("policy_timeline_event", None) + (
            " One row per dated thing that happened to a policy. Use "
            "policy_change_event or claim_event for any count."
        ),
        "timeline_event_id": "Unique id of the timeline row.",
        "policy_id": "The policy this event belongs to.",
        "event_date": (
            "When the event happened. A claim is placed on its report date; the "
            "loss date and the gap are stated in display_label."
        ),
        "event_type": (
            "One of policy_created, policy_change, claim_filed, claim_payment, "
            "renewal or status_change."
        ),
        "event_category": "Change category for change events, otherwise NULL.",
        "endorsement_id": (
            "Groups changes committed together, so the interface can show one "
            "card with several deltas."
        ),
        "coverage_line": "Coverage line for change and claim events.",
        "old_value": "Previous value as display text, for change events.",
        "new_value": "New value as display text, for change events.",
        "display_label": "Pre-rendered label, for example 'Collision limit increased'.",
        "amount": "Claim or payment amount. NULL for change events.",
        "is_material": "Whether a change event is material. False for non-change events.",
        "source_id": (
            "The change_event_id, claim_id or policy_id this row was rendered from."
        ),
    },
    # -----------------------------------------------------------------------
    "policy_pattern_match": {
        None: (
            "One row per policy and matched noteworthy pattern. A noteworthy "
            "pattern is a named, documented, deterministic rule that a policy's "
            "history matches, never a score and never a judgment about a person. "
            "A policy that matches is an investigation candidate and nothing more."
        ),
        "policy_id": "The policy that matched.",
        "pattern_code": "Stable code of the rule that matched.",
        "pattern_name": "Human-readable name of the rule, shown to users verbatim.",
        "matched_on_date": (
            "Date of the change or loss the match is anchored on. When a rule "
            "fires more than once, the most recent occurrence is kept."
        ),
        "evidence_change_event_id": "The change event that evidences the match, if any.",
        "evidence_claim_id": "The claim that evidences the match, if any.",
        "evidence_summary": "A short explanation of what matched, shown to users verbatim.",
    },
    # -----------------------------------------------------------------------
    "policy_similarity": {
        None: (
            "Pre-computed nearest neighbours by behavioural history: change "
            "rates, category mix, claim severity and matched noteworthy patterns "
            "— never demographics. Top 20 per policy. Questions phrased as "
            "'similar', 'looks like', 'histories like' or 'policies like this "
            "one' are answered from this table; never compute similarity from "
            "raw columns."
        ),
        "policy_id": "The policy whose neighbours these are.",
        "similar_policy_id": (
            "A neighbour policy. Directional: this policy appearing in another's "
            "top 20 does not imply the reverse."
        ),
        "rank": (
            "Dense rank 1 to 20, ordered by similarity_score descending then "
            "similar_policy_id ascending. 20 is the cap."
        ),
        "similarity_score": (
            "Unitless closeness, higher is closer. Comparable within one "
            "generation of the dataset, not across generations."
        ),
        "top_reasons": (
            "The named feature dimensions on which the two histories are closest."
        ),
    },
}


# ---------------------------------------------------------------------------
# Self-checks at import time
# ---------------------------------------------------------------------------

def _validate() -> None:
    if set(COMMENTS) != set(SCHEMAS):
        raise AssertionError(
            f"comment tables {sorted(COMMENTS)} do not match schemas {sorted(SCHEMAS)}"
        )
    for table, schema in SCHEMAS.items():
        documented = set(COMMENTS[table]) - {None}
        declared = {name for name, _ in schema}
        if documented != declared:
            raise AssertionError(
                f"{table}: undocumented {sorted(declared - documented)}, "
                f"unknown {sorted(documented - declared)}"
            )
        if None not in COMMENTS[table]:
            raise AssertionError(f"{table}: missing table comment")
    for (table, column), text in VERBATIM.items():
        if text not in COMMENTS[table][column]:
            raise AssertionError(
                f"{table}.{column or '<table>'} no longer quotes spec 02 §9 verbatim"
            )
    # E18 applies to comments too: they surface in Genie's answers.
    for table, columns in COMMENTS.items():
        for column, text in columns.items():
            violations = vocabulary_violations(text)
            if violations:
                raise AssertionError(
                    f"{table}.{column or '<table>'} uses banned vocabulary: {violations}"
                )


_validate()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _literal(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"


def _identifier(name: str) -> str:
    """Backtick-quote — ``rank`` is a reserved word."""
    return f"`{name}`"


def render_statements(
    catalog: str = DEFAULT_CATALOG, schema: str = DEFAULT_SCHEMA
) -> Iterator[str]:
    """Yield one ``COMMENT ON`` statement per comment.

    ``COMMENT ON COLUMN`` rather than ``ALTER TABLE ... ALTER COLUMN``:
    the curated datasets materialise as Unity Catalog materialized views,
    where ALTER TABLE fails with EXPECT_TABLE_NOT_VIEW. COMMENT ON COLUMN
    works uniformly for both tables and views.
    """
    for table in SCHEMAS:
        qualified = f"{_identifier(catalog)}.{_identifier(schema)}.{_identifier(table)}"
        yield f"COMMENT ON TABLE {qualified} IS {_literal(COMMENTS[table][None])};"
        for column, _kind in SCHEMAS[table]:
            yield (
                f"COMMENT ON COLUMN {qualified}.{_identifier(column)} "
                f"IS {_literal(COMMENTS[table][column])};"
            )


def render_script(
    catalog: str = DEFAULT_CATALOG, schema: str = DEFAULT_SCHEMA
) -> str:
    header = (
        "-- Unity Catalog comments for the Policy Time Machine Genie space.\n"
        "-- Generated from pipeline/uc_comments.py; do not edit by hand.\n"
        "-- Comments are semantic-layer content, not documentation (ADR-0013).\n"
    )
    return header + "\n" + "\n".join(render_statements(catalog, schema)) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    catalog = argv[0] if len(argv) > 0 else DEFAULT_CATALOG
    schema = argv[1] if len(argv) > 1 else DEFAULT_SCHEMA
    sys.stdout.write(render_script(catalog, schema))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
