"""The fifteen query contracts (spec 05), each an assertion against the
GROUND TRUTH computed by `ground_truth.py` — never against Genie's SQL
text and never against exact cardinality (ADR-0015).

Each contract exposes:
  - `question` (or `turns` for the one multi-turn contract, QC-15)
  - `contract_type` (cohort / ranking / comparison / table-routed)
  - `check(result, gt) -> CheckOutcome`
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .assertions import (
    banned_terms_present,
    col_values,
    extract_policy_ids,
    find_col,
    find_cols_any,
    has_terminal_data,
    row_blob,
)
from .genie_client import GenieResult
from .ground_truth import BANNED_VOCABULARY, DECLARED_CATEGORY_ORDER, VALID_PATTERN_NAMES, GroundTruth


@dataclass
class CheckOutcome:
    passed: bool
    detail: str


def _fail(detail: str) -> CheckOutcome:
    return CheckOutcome(False, detail)


def _ok(detail: str) -> CheckOutcome:
    return CheckOutcome(True, detail)


def _require_terminal(result: GenieResult) -> CheckOutcome | None:
    if result.status == "error":
        return _fail(f"Genie returned an error: {result.error}")
    if result.status == "clarification":
        return _fail(f"Genie asked a clarifying question instead of answering: {result.description!r}")
    if result.status == "empty":
        return _fail("Genie's SQL executed but returned zero rows.")
    if not has_terminal_data(result):
        return _fail(f"No usable data (status={result.status!r}).")
    return None


def _ordering_check(categories_in_order: list[str], declared: list[str]) -> CheckOutcome:
    seen = []
    for c in categories_in_order:
        c_norm = str(c).strip().lower()
        if c_norm in declared and c_norm not in seen:
            seen.append(c_norm)
    if not seen:
        return _fail(
            f"No declared category ({declared}) found among returned values {categories_in_order!r}."
        )
    expected_subsequence = [c for c in declared if c in seen]
    if seen != expected_subsequence:
        return _fail(
            f"Returned category order {seen} does not match declared ordering "
            f"{expected_subsequence} (full declared order: {declared})."
        )
    return _ok(f"Returned category order {seen} matches declared ordering.")


# --------------------------------------------------------------------------
# QC-01
# --------------------------------------------------------------------------
def check_qc01(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    date_idx = find_cols_any(result.columns, ("date",))
    if date_idx is None:
        return _fail(f"No date column found among {result.columns}.")

    missing = []
    for ev in gt.qc01_must_include:
        date_str = str(ev["event_date"])
        category = ev.get("event_category")
        event_type = ev["event_type"]
        keyword = {
            "address": "address",
            "coverage": "coverage",
            "vehicle": "vehicle",
        }.get(category, "claim" if event_type == "claim_filed" else "")
        found = False
        for row in result.rows:
            row_date = str(row[date_idx]) if date_idx < len(row) else ""
            if row_date.startswith(date_str) and keyword in row_blob(row):
                found = True
                break
        if not found:
            missing.append(f"{date_str} {category or event_type}")
    if missing:
        return _fail(f"Missing planted timeline events: {missing}.")

    excluded_present = [
        row for row in result.rows
        if date_idx < len(row) and str(row[date_idx]) < gt.qc01_must_exclude_before
    ]
    if excluded_present:
        return _fail(
            f"{len(excluded_present)} row(s) dated before the window start "
            f"({gt.qc01_must_exclude_before}) were returned."
        )

    dates = [str(row[date_idx]) for row in result.rows if date_idx < len(row)]
    if dates != sorted(dates):
        return _fail(f"Rows are not ordered by date: {dates}.")

    return _ok("All four planted timeline events present, nothing before the window, ordered by date.")


# --------------------------------------------------------------------------
# QC-02
# --------------------------------------------------------------------------
def check_qc02(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    date_idx = find_cols_any(result.columns, ("date",))
    if date_idx is None:
        return _fail(f"No date column found among {result.columns}.")

    missing = []
    for ch in gt.qc02_must_include:
        date_str = str(ch["change_date"])
        keyword = ch["change_category"]
        found = any(
            date_idx < len(row) and str(row[date_idx]).startswith(date_str) and keyword in row_blob(row)
            for row in result.rows
        )
        if not found:
            missing.append(f"{date_str} {keyword}")
    if missing:
        return _fail(f"Missing planted material changes preceding the claim: {missing}.")

    after_loss = [
        row for row in result.rows
        if date_idx < len(row) and str(row[date_idx]) > gt.qc02_loss_date
    ]
    if after_loss:
        return _fail(f"{len(after_loss)} row(s) dated after the loss date ({gt.qc02_loss_date}).")

    timing_idx = find_col(result.columns, "timing")
    if timing_idx is not None:
        bad_timing = [v for v in col_values(result, timing_idx) if v == "after_loss_before_report"]
        if bad_timing:
            return _fail("Result contains rows with change_timing = 'after_loss_before_report'.")

    return _ok("All three planted material changes present, nothing after the loss date.")


# --------------------------------------------------------------------------
# QC-03 — guards ADR-0004's critical instruction
# --------------------------------------------------------------------------
def check_qc03(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    ids = extract_policy_ids(result)
    if ids is None:
        return _fail(f"No policy_id-like column found among {result.columns}.")

    missing_s1 = gt.qc03_s1_ids - ids
    if missing_s1:
        return _fail(f"Missing {len(missing_s1)} S1 policies from the cohort: {sorted(missing_s1)[:5]}...")

    wrong_controls = ids & gt.qc03_exclude_ids
    if wrong_controls:
        return _fail(f"Cohort wrongly includes C1/C2 control policies: {sorted(wrong_controls)[:5]}...")

    trapped = ids & gt.qc03_trap_ids
    if trapped:
        return _fail(
            "ADR-0004 violation: cohort includes policies only reachable via a bare "
            f"`days_to_next_claim_loss <= 30` filter (sign/timing guard missing): {sorted(trapped)[:5]}..."
        )

    timing_idx = find_col(result.columns, "timing")
    if timing_idx is not None:
        bad_timing = [v for v in col_values(result, timing_idx) if v == "after_loss_before_report"]
        if bad_timing:
            return _fail("Returned rows include change_timing = 'after_loss_before_report'.")

    direction_idx = find_col(result.columns, "direction")
    if direction_idx is not None:
        bad_dir = [v for v in col_values(result, direction_idx) if v not in (None, "increase")]
        if bad_dir:
            return _fail(f"Returned rows include change_direction != 'increase': {set(bad_dir)}.")

    days_idx = find_col(result.columns, "days_to_next_claim_loss") or find_col(
        result.columns, "days", "claim"
    )
    if days_idx is not None:
        bad_days = [v for v in col_values(result, days_idx) if v is not None and float(v) > 30]
        if bad_days:
            return _fail(f"Returned rows include days_to_next_claim_loss > 30: {bad_days[:5]}.")

    return _ok(
        f"All 40 S1 policies present, C1/C2 excluded, trap set excluded ({len(ids)} distinct policies returned)."
    )


# --------------------------------------------------------------------------
# QC-04
# --------------------------------------------------------------------------
def check_qc04(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    ids = extract_policy_ids(result)
    if ids is None:
        return _fail(f"No policy_id-like column found among {result.columns}.")

    missing = gt.qc04_s4_ids - ids
    if missing:
        return _fail(f"Missing {len(missing)} S4 policies from the cohort: {sorted(missing)[:5]}...")

    wrong_controls = ids & gt.qc04_exclude_ids
    if wrong_controls:
        return _fail(f"Cohort wrongly includes C1/C2 control policies: {sorted(wrong_controls)[:5]}...")

    sev_idx = find_col(result.columns, "severity")
    if sev_idx is not None:
        bad_sev = [v for v in col_values(result, sev_idx) if v not in ("severe", "catastrophic")]
        if bad_sev:
            return _fail(f"Returned rows include non-high severity: {set(bad_sev)}.")

    return _ok(f"All 30 S4 policies present, C1/C2 excluded ({len(ids)} distinct policies returned).")


# --------------------------------------------------------------------------
# QC-05 — ranking
# --------------------------------------------------------------------------
def check_qc05(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    cat_idx = find_cols_any(result.columns, ("categor",), ("field",))
    if cat_idx is None:
        return _fail(f"No change-category column found among {result.columns}.")
    categories = col_values(result, cat_idx)
    return _ordering_check(categories, DECLARED_CATEGORY_ORDER)


# --------------------------------------------------------------------------
# QC-06 — ranking + negative on amount
# --------------------------------------------------------------------------
def check_qc06(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    cat_idx = find_cols_any(result.columns, ("categor",), ("field",))
    if cat_idx is None:
        return _fail(f"No change-category column found among {result.columns}.")
    ordering = _ordering_check(col_values(result, cat_idx), DECLARED_CATEGORY_ORDER)
    if not ordering.passed:
        return ordering

    amount_idx = find_col(result.columns, "amount")
    if amount_idx is not None:
        low_amounts = [v for v in col_values(result, amount_idx) if v is not None and float(v) <= 25000]
        if low_amounts:
            return _fail(f"Returned rows include claim amounts <= $25,000: {low_amounts[:5]}.")

    return _ok(ordering.detail + " No claim amount at or below $25,000.")


# --------------------------------------------------------------------------
# QC-07
# --------------------------------------------------------------------------
def check_qc07(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    ids = extract_policy_ids(result)
    if ids is None:
        return _fail(f"No policy_id-like column found among {result.columns}.")

    missing = gt.qc07_s2_ids - ids
    if missing:
        return _fail(f"Missing {len(missing)} S2 policies from the cohort: {sorted(missing)[:5]}...")

    wrong_controls = ids & gt.qc07_exclude_ids
    if wrong_controls:
        return _fail(f"Cohort wrongly includes C1 control policies: {sorted(wrong_controls)[:5]}...")

    cat_idx = find_col(result.columns, "categor")
    if cat_idx is not None:
        bad_cat = [v for v in col_values(result, cat_idx) if v != "deductible"]
        if bad_cat:
            return _fail(f"Returned rows include change_category != 'deductible': {set(bad_cat)}.")

    direction_idx = find_col(result.columns, "direction")
    if direction_idx is not None:
        bad_dir = [v for v in col_values(result, direction_idx) if v != "decrease"]
        if bad_dir:
            return _fail(f"Returned rows include change_direction != 'decrease': {set(bad_dir)}.")

    line_idx = find_col(result.columns, "coverage", "line") or find_col(result.columns, "line")
    if line_idx is not None:
        bad_line = [v for v in col_values(result, line_idx) if v not in ("COLL", "COMP")]
        if bad_line:
            return _fail(f"Returned rows include a coverage line outside COLL/COMP: {set(bad_line)}.")

    # The question carries an explicit 90-day window (spec 05 QC-07, ADR-0004):
    # under report-date-anchored linkage a bare `before_loss` filter with no
    # window legitimately admits a C1 policy's far-prior, unrelated deductible
    # decrease, which is what the exclude-C1 assertion above would otherwise
    # be unable to distinguish from a defect.
    days_idx = find_col(result.columns, "days_to_next_claim_loss") or find_col(
        result.columns, "days", "claim"
    )
    if days_idx is not None:
        bad_days = [v for v in col_values(result, days_idx) if v is not None and float(v) > 90]
        if bad_days:
            return _fail(f"Returned rows include days_to_next_claim_loss > 90: {bad_days[:5]}.")

    return _ok(f"All 30 S2 policies present, C1 excluded ({len(ids)} distinct policies returned).")


# --------------------------------------------------------------------------
# QC-08
# --------------------------------------------------------------------------
def check_qc08(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    ids = extract_policy_ids(result)
    if ids is None:
        return _fail(f"No policy_id-like column found among {result.columns}.")

    missing = gt.qc08_s5_ids - ids
    if missing:
        return _fail(f"Missing {len(missing)} S5 policies from the cohort: {sorted(missing)[:5]}...")

    offset_idx = find_col(result.columns, "offset")
    if offset_idx is not None:
        bad_offset = [
            v for v in col_values(result, offset_idx)
            if v is not None and abs(float(v)) > 60
        ]
        if bad_offset:
            return _fail(f"Returned rows include |offset| > 60 days: {bad_offset[:5]}.")

    return _ok(f"All 35 S5 policies present ({len(ids)} distinct policies returned).")


# --------------------------------------------------------------------------
# QC-09 — table-routed
# --------------------------------------------------------------------------
def check_qc09(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    cust_idx = find_col(result.columns, "customer")
    if cust_idx is None:
        return _fail(f"No customer_id column found among {result.columns}.")
    returned_top = [str(row[cust_idx]) for row in result.rows[:10] if cust_idx < len(row)]
    expected_top = [r["customer_id"] for r in gt.qc09_top10]
    if returned_top != expected_top:
        return _fail(f"Top-10 mismatch. Expected {expected_top}, got {returned_top}.")
    return _ok("Top-10 customers by material_change_count match policy_profile exactly, in order.")


# --------------------------------------------------------------------------
# QC-10 — comparison
# --------------------------------------------------------------------------
def check_qc10(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    if len(result.rows) != 2:
        return _fail(f"Expected exactly two groups, got {len(result.rows)} row(s).")

    label_idx = find_cols_any(result.columns, ("group",), ("label",), ("comparison",), ("segment",))
    n_idx = find_cols_any(result.columns, ("n",), ("count",), ("polic",), ("num",))
    rate_idx = find_cols_any(result.columns, ("rate",), ("frequency",), ("claims_per_year",), ("avg",))

    if label_idx is None:
        return _fail(f"No group-label column found among {result.columns}.")
    if n_idx is None:
        return _fail(f"No sample-size (n) column found among {result.columns}.")
    if rate_idx is None:
        return _fail(f"No rate column found among {result.columns}.")

    ns = col_values(result, n_idx)
    floor = min(gt.qc10_n_recent, gt.qc10_n_not_recent) * 0.5
    for n in ns:
        try:
            n_val = float(n)
        except (TypeError, ValueError):
            return _fail(f"Non-numeric n value: {n!r}.")
        if n_val <= floor:
            return _fail(
                f"Group n={n_val} does not exceed the ground-truth-derived floor "
                f"({floor:.0f}, half of min(recent={gt.qc10_n_recent}, not_recent={gt.qc10_n_not_recent}))."
            )

    labels = col_values(result, label_idx)
    if len(set(str(l).lower() for l in labels)) != 2:
        return _fail(f"Group labels are not distinct: {labels}.")

    return _ok(f"Two distinct groups returned, both with label/rate/n; n values {ns} clear the floor.")


# --------------------------------------------------------------------------
# QC-11 — table-routed
# --------------------------------------------------------------------------
def check_qc11(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    if len(result.rows) > 20:
        return _fail(f"Returned {len(result.rows)} rows; similarity is capped at 20.")

    rank_idx = find_col(result.columns, "rank")
    neighbour_idx = find_col(result.columns, "similar", "polic") or find_col(result.columns, "polic", "id")
    if rank_idx is None or neighbour_idx is None:
        return _fail(f"No rank/neighbour-policy column pair found among {result.columns}.")

    returned = [
        (int(row[rank_idx]), str(row[neighbour_idx]))
        for row in result.rows
        if rank_idx < len(row) and neighbour_idx < len(row)
    ]
    returned.sort(key=lambda t: t[0])
    expected = [(int(r["rank"]), str(r["similar_policy_id"])) for r in gt.qc11_neighbours]
    if returned != expected[: len(returned)] or len(returned) != len(expected):
        return _fail(f"Neighbour list does not match policy_similarity exactly. Expected {expected}, got {returned}.")

    return _ok(f"All {len(expected)} neighbours match policy_similarity exactly, in rank order.")


# --------------------------------------------------------------------------
# QC-12
# --------------------------------------------------------------------------
def check_qc12(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    ids = extract_policy_ids(result)
    if ids is None:
        # Fall back to scanning every cell for a C1 policy id, in case the
        # id column wasn't detected by name.
        blob = " ".join(row_blob(row) for row in result.rows)
        hit = any(pid.lower() in blob for pid in gt.qc12_c1_top_claim_ids)
        if not hit:
            return _fail(
                "No policy_id column found and no C1 top-claim policy id appears anywhere in the "
                f"result. C1 policies among the top claims: {sorted(gt.qc12_c1_top_claim_ids)}."
            )
        return _ok("A C1 (large-claim-no-preceding-change) policy id appears in the result text.")

    hit = ids & gt.qc12_c1_top_claim_ids
    if not hit:
        return _fail(
            "Result implies every large claim has a preceding change — no C1 policy "
            f"(large claim, no preceding change) present. C1 candidates: {sorted(gt.qc12_c1_top_claim_ids)}."
        )
    return _ok(f"Result includes at least one C1 policy with no preceding change: {sorted(hit)}.")


# --------------------------------------------------------------------------
# QC-13 — ranking + comparison + vocabulary
# --------------------------------------------------------------------------
def check_qc13(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad

    all_text_parts = [result.description or ""]
    for row in result.rows:
        all_text_parts.append(row_blob(row))
    all_text_parts.extend(result.columns)
    hits = banned_terms_present(" ".join(all_text_parts), BANNED_VOCABULARY)
    if hits:
        return _fail(f"Banned vocabulary present in Genie's answer: {hits}.")

    cat_idx = find_cols_any(result.columns, ("categor",), ("field",), ("change_type",))
    if cat_idx is not None:
        ordering = _ordering_check(col_values(result, cat_idx), DECLARED_CATEGORY_ORDER)
        if not ordering.passed:
            return ordering

    baseline_idx = find_cols_any(
        result.columns, ("baseline",), ("compar",), ("control",), ("rate",), ("frequency",)
    )
    if baseline_idx is None:
        return _fail(f"No baseline/comparison figure column found among {result.columns}.")

    return _ok("No banned vocabulary, ordering (where present) matches declared, carries a comparison figure.")


# --------------------------------------------------------------------------
# QC-14 — table-routed
# --------------------------------------------------------------------------
def check_qc14(result: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad = _require_terminal(result)
    if bad:
        return bad
    name_idx = find_col(result.columns, "pattern", "name") or find_col(result.columns, "pattern")
    count_idx = find_cols_any(result.columns, ("count",), ("polic",), ("n",))
    if name_idx is None:
        return _fail(f"No pattern_name column found among {result.columns}.")

    invalid_names = [
        v for v in col_values(result, name_idx) if v not in VALID_PATTERN_NAMES
    ]
    if invalid_names:
        return _fail(f"Returned pattern_name(s) outside the six defined codes: {set(invalid_names)}.")

    if count_idx is not None:
        mismatches = []
        for row in result.rows:
            name = row[name_idx]
            got = row[count_idx] if count_idx < len(row) else None
            expected = gt.qc14_pattern_counts.get(name)
            if expected is not None and got is not None and int(got) != expected:
                mismatches.append((name, got, expected))
        if mismatches:
            return _fail(f"Pattern counts do not match policy_pattern_match exactly: {mismatches}.")

    return _ok("Every returned pattern_name is one of the six defined codes; counts match where present.")


# --------------------------------------------------------------------------
# QC-15 — multi-turn
# --------------------------------------------------------------------------
def check_qc15(turn1: GenieResult, turn2: GenieResult, gt: GroundTruth) -> CheckOutcome:
    bad1 = _require_terminal(turn1)
    if bad1:
        return _fail(f"Turn 1 (QC-03): {bad1.detail}")
    turn1_check = check_qc03(turn1, gt)
    if not turn1_check.passed:
        return _fail(f"Turn 1 (QC-03) failed its own contract: {turn1_check.detail}")

    bad2 = _require_terminal(turn2)
    if bad2:
        return _fail(f"Turn 2: {bad2.detail}")

    ids1 = extract_policy_ids(turn1)
    ids2 = extract_policy_ids(turn2)
    if ids1 is None or ids2 is None:
        return _fail(f"Could not locate policy_id column in turn 1 ({turn1.columns}) or turn 2 ({turn2.columns}).")

    if not ids2.issubset(ids1):
        extra = ids2 - ids1
        return _fail(f"Turn 2's cohort is not a subset of turn 1's: {sorted(extra)[:5]}... are new.")

    missing_s6 = gt.qc15_s6_ids - ids2
    if missing_s6:
        return _fail(f"Turn 2 is missing {len(missing_s6)} S6 policies: {sorted(missing_s6)[:5]}...")

    return _ok(
        f"Turn 2 ({len(ids2)} policies) is a subset of turn 1 ({len(ids1)} policies) and includes all S6 policies."
    )


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
@dataclass
class Contract:
    id: str
    contract_type: str
    question: str | None
    turns: tuple[str, str] | None
    check: Callable


CONTRACTS: list[Contract] = [
    Contract("QC-01", "cohort", f"What changed on policy {{demo}} during the last year?", None, check_qc01),
    Contract("QC-02", "cohort", f"What changed before the latest claim on {{demo}}?", None, check_qc02),
    Contract(
        "QC-03", "cohort", "Show policies where coverage increased within 30 days before a claim.", None, check_qc03
    ),
    Contract(
        "QC-04",
        "cohort",
        "Find policies with several material changes before a high-severity claim.",
        None,
        check_qc04,
    ),
    Contract(
        "QC-05",
        "ranking",
        "Which material changes most often precede high-severity claims, within 60 days?",
        None,
        check_qc05,
    ),
    Contract(
        "QC-06",
        "ranking",
        "Which material changes happen most often, within 60 days, before claims above $25,000?",
        None,
        check_qc06,
    ),
    Contract(
        "QC-07",
        "cohort",
        "Show policies where deductible decreased within 90 days before a claim.",
        None,
        check_qc07,
    ),
    Contract(
        "QC-08",
        "cohort",
        "Which policies changed vehicles and addresses within 60 days?",
        None,
        check_qc08,
    ),
    Contract(
        "QC-09", "table-routed", "Which customers have the highest number of policy changes?", None, check_qc09
    ),
    Contract(
        "QC-10",
        "comparison",
        "Compare policies with recent material changes against policies without.",
        None,
        check_qc10,
    ),
    Contract(
        "QC-11", "table-routed", f"Find policies with histories similar to {{demo}}.", None, check_qc11
    ),
    Contract(
        "QC-12", "cohort", "What happened immediately before the largest claims?", None, check_qc12
    ),
    Contract(
        "QC-13",
        "ranking+comparison",
        "Are claims more frequent, within 60 days, following specific types of material policy changes?",
        None,
        check_qc13,
    ),
    Contract(
        "QC-14",
        "table-routed",
        "Show unusual historical patterns worth investigating.",
        None,
        check_qc14,
    ),
    Contract(
        "QC-15",
        "cohort-multiturn",
        None,
        (
            "Show policies where coverage increased within 30 days before a claim.",
            "Of these, which had a claim near the new limit?",
        ),
        check_qc15,
    ),
]
