"""Policy Time Machine — semantic-layer transformation logic.

Pure Python + pandas. **No PySpark import anywhere in this module**, so every rule
that `docs/specs/02-semantic-layer.md` and the ADRs make load-bearing can be unit
tested on a laptop against hand-built fixtures. `dlt_pipeline.py` is a thin shim
that reads the source Delta tables, hands the pandas frames to the ``build_*``
functions below, and writes the results back with the expectations attached.

There is exactly one implementation of every subtle rule. That is deliberate:

* ADR-0008 requires ``policy_change_event.next_claim_severity`` and
  ``claim_event.severity_band`` to come from the same code path (:func:`severity_band`).
* ADR-0009 requires the ``policy_pattern_match`` rows and the ``policy_profile``
  booleans to come from **one** rule evaluation pass, never from a second copy of
  the predicate (:func:`build_policy_pattern_match` feeds :func:`build_policy_profile`).

Reading order: `CONTEXT.md`, then `docs/specs/02-semantic-layer.md`, then ADR-0004
(claim linkage on report date), ADR-0009 (patterns), ADR-0010 (similarity).

Terminology follows CONTEXT.md exactly. Where this module had to resolve something
the specs leave open, the decision is marked ``AMBIGUITY:`` in a comment.
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

# ---------------------------------------------------------------------------
# Vocabulary and fixed constants
# ---------------------------------------------------------------------------

#: The five decision categories (ADR-0003). Only these are counted as material.
MATERIAL_CATEGORIES: tuple[str, ...] = ("coverage", "deductible", "vehicle", "address", "status")

#: Tracked, visible on a timeline, never material (ADR-0003).
DERIVED_CATEGORIES: tuple[str, ...] = ("premium", "agent")

ALL_CATEGORIES: tuple[str, ...] = MATERIAL_CATEGORIES + DERIVED_CATEGORIES

#: Categories whose values are numeric. ``old_value_num``/``new_value_num`` are
#: populated for these and NULL for everything else (E3).
NUMERIC_CATEGORIES: tuple[str, ...] = ("coverage", "deductible", "premium")

#: Categories whose values are categorical. ``change_direction`` is always
#: ``'switch'`` here and ``change_pct`` is always NULL (E1, E2).
CATEGORICAL_CATEGORIES: tuple[str, ...] = ("vehicle", "address", "status", "agent")

COVERAGE_LINES: tuple[str, ...] = ("BI", "PD", "COLL", "COMP", "UMUIM")

#: Only these lines carry a deductible (spec 01 §1, E12).
DEDUCTIBLE_LINES: tuple[str, ...] = ("COLL", "COMP")

LINE_NAMES: dict[str, str] = {
    "BI": "Bodily injury liability",
    "PD": "Property damage liability",
    "COLL": "Collision",
    "COMP": "Comprehensive",
    "UMUIM": "Uninsured/underinsured motorist",
}

#: Half-open severity cuts (ADR-0008). They partition ``[0, inf)`` with no gap
#: and no overlap, which is expectation E9.
SEVERITY_CUTS: tuple[tuple[str, float, float], ...] = (
    ("minor", 0.0, 2500.0),
    ("moderate", 2500.0, 10000.0),
    ("severe", 10000.0, 50000.0),
    ("catastrophic", 50000.0, math.inf),
)

SEVERITY_ORDER: tuple[str, ...] = ("minor", "moderate", "severe", "catastrophic")
SEVERITY_ORDINAL: dict[str, int] = {b: i + 1 for i, b in enumerate(SEVERITY_ORDER)}

#: "High-severity" is severe or catastrophic. The product's own definition.
HIGH_SEVERITY_BANDS: tuple[str, ...] = ("severe", "catastrophic")

#: ``at_or_near_limit`` threshold, a named constant (ADR-0008).
AT_OR_NEAR_LIMIT_PCT: float = 90.0

#: Baked pattern windows (ADR-0009 — a deliberate exception to spec 02 §1).
PATTERN_CLAIM_WINDOW_DAYS: int = 60
PATTERN_CLUSTER_SPAN_DAYS: int = 30
PATTERN_CLUSTER_MIN_CHANGES: int = 3
PATTERN_VEHICLE_ADDRESS_DAYS: int = 60
PATTERN_LIMIT_RAISED_WINDOW_DAYS: int = 90

#: Similarity (ADR-0010).
K_NEIGHBOURS: int = 20
#: AMBIGUITY: ADR-0010 says Jaccard on the pattern-code set is "a separately
#: weighted component" but never states the weight. 2.0 is chosen so a completely
#: disjoint pattern set costs the same as being two standard deviations apart on
#: one numeric dimension — patterns matter, but do not dominate twelve numerics.
PATTERN_WEIGHT: float = 2.0
#: Scores are rounded before ordering so the documented tie-break
#: (``similarity_score DESC, similar_policy_id ASC``) is reachable at all:
#: unrounded floats almost never tie, which would make the tie-break dead code
#: and regeneration ordering depend on float noise (ADR-0010).
SIMILARITY_SCORE_DECIMALS: int = 6

#: Approved vocabulary, spec 03 §7. E18 is enforced as the absence of any banned
#: term (see :func:`vocabulary_violations`).
APPROVED_VOCABULARY: tuple[str, ...] = (
    "noteworthy", "unusual pattern", "investigation candidate", "historical pattern",
    "requires review", "worth investigating", "associated with", "observed alongside",
    "occurred before",
)

#: Never use (spec 03 §7 / ADR-0014). Two bans in one list: accusatory language
#: about people, and causal language about the data.
BANNED_VOCABULARY: tuple[str, ...] = (
    "fraud", "fraudulent", "suspicious", "scheme", "deceptive", "guilty",
    "risk score", "predicts", "causes", "leads to", "increases the risk of",
    # Not in the spec's own list but named in CONTEXT.md's _Avoid_ lines and in
    # the task brief as forbidden in user-facing strings.
    "anomaly", "anomalous", "red flag",
)

#: The app detects policy references with this pattern (spec 01 §2, ADR-0007).
#: No identifier of any other type may match it (E19).
POLICY_ID_PATTERN: re.Pattern[str] = re.compile(r"\bP-\d{5}\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Declared output schemas — shared by the pandas cast here and the Spark schema
# built in dlt_pipeline.py, so the two can never disagree.
# ---------------------------------------------------------------------------

POLICY_CHANGE_EVENT_SCHEMA: tuple[tuple[str, str], ...] = (
    ("change_event_id", "string"), ("policy_id", "string"), ("customer_id", "string"),
    ("endorsement_id", "string"), ("change_date", "date"), ("change_category", "string"),
    ("is_material", "boolean"), ("coverage_line", "string"),
    ("old_value", "string"), ("new_value", "string"),
    ("old_value_num", "decimal"), ("new_value_num", "decimal"),
    ("change_direction", "string"), ("change_pct", "decimal"),
    ("next_claim_id", "string"), ("days_to_next_claim_loss", "int"),
    ("days_to_next_claim_report", "int"), ("change_timing", "string"),
    ("next_claim_amount", "decimal"), ("next_claim_severity", "string"),
    ("next_claim_coverage_line", "string"), ("change_relates_to_claimed_coverage", "boolean"),
    ("nearest_coverage_change_offset_days", "int"), ("nearest_deductible_change_offset_days", "int"),
    ("nearest_vehicle_change_offset_days", "int"), ("nearest_address_change_offset_days", "int"),
    ("nearest_status_change_offset_days", "int"),
    ("material_changes_prior_30d", "int"), ("material_changes_prior_60d", "int"),
    ("material_changes_prior_90d", "int"),
    ("policy_start_date", "date"), ("policy_state", "string"),
)

#: The seven columns E4 requires to be NULL together or populated together.
#: ``change_relates_to_claimed_coverage`` is an eighth linkage-derived column and
#: is deliberately not in this list — spec 02 §2 says "seven".
LINKAGE_COLUMNS: tuple[str, ...] = (
    "next_claim_id", "days_to_next_claim_loss", "days_to_next_claim_report",
    "change_timing", "next_claim_amount", "next_claim_severity", "next_claim_coverage_line",
)

CLAIM_EVENT_SCHEMA: tuple[tuple[str, str], ...] = (
    ("claim_id", "string"), ("policy_id", "string"), ("customer_id", "string"),
    ("coverage_line", "string"), ("loss_date", "date"), ("report_date", "date"),
    ("loss_to_report_days", "int"), ("settled_amount", "decimal"), ("severity_band", "string"),
    ("applicable_limit", "decimal"), ("limit_utilization_pct", "decimal"),
    ("at_or_near_limit", "boolean"), ("claim_status", "string"),
    ("material_changes_prior_30d", "int"), ("material_changes_prior_60d", "int"),
    ("material_changes_prior_90d", "int"), ("material_changes_in_loss_report_gap", "int"),
    ("days_since_last_material_change_before_loss", "int"),
    ("last_material_change_category", "string"), ("last_material_change_date", "date"),
    ("relevant_coverage_change_prior_60d", "boolean"),
)

PATTERN_CODES: tuple[str, ...] = (
    "coverage_raised_then_claimed_same_line",
    "deductible_lowered_before_claim",
    "change_in_loss_report_gap",
    "rapid_change_cluster",
    "vehicle_and_address_within_60d",
    "claim_near_new_limit",
)

#: Authored user-facing names (ADR-0009). Bound by the vocabulary rule (E18).
PATTERN_NAMES: dict[str, str] = {
    "coverage_raised_then_claimed_same_line": "Coverage raised, then a claim on the same line",
    "deductible_lowered_before_claim": "Deductible lowered before a claim",
    "change_in_loss_report_gap": "Change during the loss-to-report gap",
    "rapid_change_cluster": "Rapid change cluster",
    "vehicle_and_address_within_60d": "Vehicle and address changed within 60 days",
    "claim_near_new_limit": "Claim near a newly raised limit",
}

PATTERN_FLAG_COLUMNS: tuple[str, ...] = tuple(f"pattern_{code}" for code in PATTERN_CODES)

POLICY_PROFILE_SCHEMA: tuple[tuple[str, str], ...] = (
    # Current state
    ("policy_id", "string"), ("customer_id", "string"), ("policy_status", "string"),
    ("policy_start_date", "date"), ("term_start_date", "date"), ("term_end_date", "date"),
    ("current_city", "string"), ("current_state", "string"),
    ("current_annual_premium", "decimal"), ("current_primary_vehicle", "string"),
    ("current_coll_limit", "decimal"), ("current_comp_limit", "decimal"),
    ("current_bi_limit", "decimal"), ("current_coll_deductible", "decimal"),
    ("current_comp_deductible", "decimal"),
    # Behavioural summary
    ("material_change_count", "int"), ("material_changes_per_year", "decimal"),
    ("peak_material_changes_30d", "int"),
    ("coverage_change_count", "int"), ("deductible_change_count", "int"),
    ("vehicle_change_count", "int"), ("address_change_count", "int"),
    ("status_change_count", "int"), ("net_coverage_direction", "string"),
    ("claim_count", "int"), ("claims_per_year", "decimal"),
    ("max_severity_band", "string"), ("mean_limit_utilization", "decimal"),
    ("share_material_changes_within_60d_before_loss", "decimal"),
    # Recency — DATES ONLY. Never a day-count (E20, ADR-0006).
    ("last_material_change_date", "date"), ("last_claim_date", "date"),
    # Pattern flags (ADR-0009), derived from the single pattern pass.
    ("noteworthy_pattern_count", "int"),
) + tuple((col, "boolean") for col in PATTERN_FLAG_COLUMNS)

POLICY_TIMELINE_EVENT_SCHEMA: tuple[tuple[str, str], ...] = (
    ("timeline_event_id", "string"), ("policy_id", "string"), ("event_date", "date"),
    ("event_type", "string"), ("event_category", "string"), ("endorsement_id", "string"),
    ("coverage_line", "string"), ("old_value", "string"), ("new_value", "string"),
    ("display_label", "string"), ("amount", "decimal"), ("is_material", "boolean"),
    ("source_id", "string"),
)

TIMELINE_EVENT_TYPES: tuple[str, ...] = (
    "policy_created", "policy_change", "claim_filed", "claim_payment", "renewal", "status_change",
)

POLICY_PATTERN_MATCH_SCHEMA: tuple[tuple[str, str], ...] = (
    ("policy_id", "string"), ("pattern_code", "string"), ("pattern_name", "string"),
    ("matched_on_date", "date"), ("evidence_change_event_id", "string"),
    ("evidence_claim_id", "string"), ("evidence_summary", "string"),
)

POLICY_SIMILARITY_SCHEMA: tuple[tuple[str, str], ...] = (
    ("policy_id", "string"), ("similar_policy_id", "string"), ("rank", "int"),
    ("similarity_score", "decimal"), ("top_reasons", "string"),
)

SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "policy_change_event": POLICY_CHANGE_EVENT_SCHEMA,
    "claim_event": CLAIM_EVENT_SCHEMA,
    "policy_profile": POLICY_PROFILE_SCHEMA,
    "policy_timeline_event": POLICY_TIMELINE_EVENT_SCHEMA,
    "policy_pattern_match": POLICY_PATTERN_MATCH_SCHEMA,
    "policy_similarity": POLICY_SIMILARITY_SCHEMA,
}

#: The silver-layer change stream (medallion: ptm_bronze -> ptm_silver ->
#: ptm_gold). Deliberately not in :data:`SCHEMAS`, whose keys are asserted
#: equal to the gold tables by uc_comments and the test suite. Matches the
#: column list :func:`derive_change_events_from_scd2` returns.
CHANGE_EVENT_SCHEMA: tuple[tuple[str, str], ...] = (
    ("change_event_id", "string"), ("policy_id", "string"),
    ("endorsement_id", "string"), ("change_date", "date"),
    ("change_category", "string"), ("coverage_line", "string"),
    ("old_value", "string"), ("new_value", "string"),
    ("old_value_num", "decimal"), ("new_value_num", "decimal"),
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _is_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def to_date(value: Any) -> _dt.date | None:
    """Coerce anything date-ish to ``datetime.date``; NULL-ish to ``None``."""
    if _is_null(value):
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return pd.Timestamp(value).date()


def to_num(value: Any) -> float | None:
    if _is_null(value):
        return None
    return float(value)


def to_str(value: Any) -> str | None:
    if _is_null(value):
        return None
    return str(value)


def days_between(later: _dt.date, earlier: _dt.date) -> int:
    return (later - earlier).days


def records(frame: Any) -> list[dict[str, Any]]:
    """Normalise a pandas DataFrame or a sequence of mappings to plain dicts."""
    if frame is None:
        return []
    if isinstance(frame, pd.DataFrame):
        return [
            {k: (None if _is_null(v) else v) for k, v in row.items()}
            for row in frame.to_dict("records")
        ]
    return [dict(row) for row in frame]


def _group_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row.get(key), []).append(dict(row))
    return out


def frame(rows: Sequence[Mapping[str, Any]], schema: Sequence[tuple[str, str]]) -> pd.DataFrame:
    """Build a DataFrame with the declared column order and nullable dtypes.

    Dates stay as ``datetime.date`` objects rather than ``datetime64`` so that a
    test can compare them to a literal ``date(...)`` and so Spark maps them to
    ``DateType`` without a timestamp round-trip.
    """
    columns = [name for name, _ in schema]
    data = [{col: row.get(col) for col in columns} for row in rows]
    df = pd.DataFrame(data, columns=columns)
    for name, kind in schema:
        if kind == "int":
            df[name] = pd.array(
                [None if _is_null(v) else int(v) for v in df[name]], dtype="Int64"
            )
        elif kind == "decimal":
            df[name] = pd.array(
                [None if _is_null(v) else float(v) for v in df[name]], dtype="Float64"
            )
        elif kind == "boolean":
            df[name] = pd.array(
                [None if _is_null(v) else bool(v) for v in df[name]], dtype="boolean"
            )
        elif kind == "date":
            df[name] = pd.Series([to_date(v) for v in df[name]], dtype="object")
        else:
            df[name] = pd.Series([to_str(v) for v in df[name]], dtype="object")
    return df


# ---------------------------------------------------------------------------
# Vocabulary and identifier guards (E18, E19)
# ---------------------------------------------------------------------------

_BANNED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (term, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE))
    for term in BANNED_VOCABULARY
)


def vocabulary_violations(text: Any) -> list[str]:
    """Banned terms found in a user-facing string (E18).

    AMBIGUITY: E18 reads "contains a term outside the approved vocabulary", which
    taken literally would allow only the nine approved phrases and forbid every
    ordinary English word. ADR-0009 and ADR-0014 state the intent — "never fraud,
    suspicious, or any assertion about a person" — so E18 is implemented as the
    absence of any banned term, which is the enforceable reading.
    """
    value = to_str(text)
    if value is None:
        return []
    return [term for term, pattern in _BANNED_PATTERNS if pattern.search(value)]


def matches_policy_id_pattern(value: Any) -> bool:
    """True if a string would be mistaken for a policy reference (E19)."""
    text = to_str(value)
    return bool(text) and bool(POLICY_ID_PATTERN.search(text))


def _policy_token(policy_id: str) -> str:
    """A policy-derived token that cannot itself match ``\\bP-\\d{5}\\b`` (E19).

    Timeline event ids are derived from their source so they are stable across
    regenerations, but a naive ``TLE-P-18492`` would embed a policy reference and
    break the app's timeline routing (ADR-0007).
    """
    token = re.sub(r"(?i)^P-", "", policy_id)
    if POLICY_ID_PATTERN.search(token):  # pragma: no cover - defensive
        raise ValueError(f"policy token still matches the policy pattern: {token!r}")
    return token


# ---------------------------------------------------------------------------
# Shared scalar rules — one implementation, used on both sides of every join
# ---------------------------------------------------------------------------

def severity_band(settled_amount: Any) -> str | None:
    """Fixed dollar bands (ADR-0008). The only place the cuts appear.

    ``next_claim_severity`` on ``policy_change_event`` and ``severity_band`` on
    ``claim_event`` both call this, which is what makes E8 structurally true
    rather than coincidentally true.
    """
    amount = to_num(settled_amount)
    if amount is None:
        return None
    for band, low, high in SEVERITY_CUTS:
        if low <= amount < high:
            return band
    return None  # negative amounts fall outside the partition


def is_high_severity(band: Any) -> bool:
    return to_str(band) in HIGH_SEVERITY_BANDS


def is_material_category(category: Any) -> bool:
    return to_str(category) in MATERIAL_CATEGORIES


def change_direction(category: Any, old_num: Any, new_num: Any) -> str:
    """``increase`` | ``decrease`` | ``switch``. Never NULL (E2, ADR-0003).

    Categoricals are always ``switch`` so that "all increases" excludes them by
    value rather than by NULL handling.
    """
    cat = to_str(category)
    if cat in CATEGORICAL_CATEGORIES:
        return "switch"
    old, new = to_num(old_num), to_num(new_num)
    if old is not None and new is not None:
        return "increase" if new > old else "decrease" if new < old else "increase"
    # AMBIGUITY: the specs never describe a numeric change with a NULL or equal
    # old value; a change event exists only between two versions, so the
    # generator should not emit one. The column may not be NULL (E2 forbids it
    # for categoricals and the enum admits no fourth value), so a missing old
    # value is treated as a zero baseline and equality resolves to 'increase'.
    baseline = old if old is not None else 0.0
    return "increase" if (new or 0.0) >= baseline else "decrease"


def change_pct(category: Any, old_num: Any, new_num: Any) -> float | None:
    """Signed percentage change, or NULL. Never a sentinel, never infinity (E1)."""
    cat = to_str(category)
    if cat in CATEGORICAL_CATEGORIES:
        return None
    old, new = to_num(old_num), to_num(new_num)
    if old is None or new is None or old == 0:
        return None
    value = (new - old) / old * 100.0
    if not math.isfinite(value):  # pragma: no cover - defensive
        return None
    return round(value, 6)


def limit_utilization_pct(settled_amount: Any, applicable_limit: Any) -> float | None:
    """NULL when the limit is NULL or zero. **Never clamped above 100** (E10)."""
    amount, limit = to_num(settled_amount), to_num(applicable_limit)
    if amount is None or limit is None or limit == 0:
        return None
    return round(amount / limit * 100.0, 6)


def change_timing(days_to_loss: int | None) -> str | None:
    """``before_loss`` | ``after_loss_before_report``, NULL when unlinked (ADR-0004).

    A change dated the same day as the loss has a delta of 0 and is
    ``before_loss`` — spec 02 §2's same-day tie rule.
    """
    if days_to_loss is None:
        return None
    return "before_loss" if days_to_loss >= 0 else "after_loss_before_report"


# ---------------------------------------------------------------------------
# SCD Type 2 helpers
# ---------------------------------------------------------------------------

def _scd_lookup(versions: Sequence[Mapping[str, Any]], as_of: _dt.date) -> dict[str, Any] | None:
    """The version covering ``as_of``. ``effective_to`` is exclusive (spec 01 §3)."""
    for row in versions:
        start = to_date(row.get("effective_from"))
        end = to_date(row.get("effective_to"))
        if start is not None and start <= as_of and (end is None or as_of < end):
            return dict(row)
    return None


def _current_version(versions: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    current = [r for r in versions if bool(r.get("is_current"))]
    if current:
        return dict(max(current, key=lambda r: int(r.get("version_no") or 0)))
    if versions:
        return dict(max(versions, key=lambda r: int(r.get("version_no") or 0)))
    return None


def _policy_customer_map(policy_history: Any) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for row in records(policy_history):
        out.setdefault(to_str(row.get("policy_id")), to_str(row.get("customer_id")))
    return out


def _policy_start_dates(policy_history: Any) -> dict[str, _dt.date | None]:
    out: dict[str, _dt.date | None] = {}
    for policy_id, versions in _group_by(records(policy_history), "policy_id").items():
        starts = [to_date(v.get("effective_from")) for v in versions]
        starts = [s for s in starts if s is not None]
        out[to_str(policy_id)] = min(starts) if starts else None
    return out


# ---------------------------------------------------------------------------
# Fallback: derive change events from the SCD Type 2 sources
# ---------------------------------------------------------------------------

#: Which policy_history attribute maps to which change category (ADR-0003).
#: ``term_start_date``/``term_end_date`` are deliberately absent: renewal is a
#: Timeline Event, never a Policy Change, and renewal-driven status
#: recalculations are never emitted as change events (spec 01 §6 rule 2).
_HISTORY_FIELD_CATEGORIES: tuple[tuple[str, str, bool], ...] = (
    # (source column, change_category, numeric?)
    ("garaging_city", "address", False),
    ("garaging_state", "address", False),
    ("garaging_postal_code", "address", False),
    ("policy_status", "status", False),
    ("primary_vehicle_id", "vehicle", False),
    ("annual_premium", "premium", True),
    ("agent_id", "agent", False),
)


def derive_change_events_from_scd2(
    policy_history: Any,
    policy_coverage_history: Any,
) -> pd.DataFrame:
    """Derive the raw change-event grain by diffing consecutive SCD2 versions.

    AMBIGUITY: spec 01 §3 lists seven source tables and **no change-event table**,
    yet §2 gives change events an identifier format (``CHG-`` + 8 digits) and §4
    gives them a volume target, both of which read as generator output. Both
    readings are supported: if the generator emits a raw ``change_event`` table
    the pipeline consumes it directly; if it does not, this function reconstructs
    the same grain from ``policy_history`` and ``policy_coverage_history``.

    An address change touching city, state and postal code together is emitted as
    **one** ``address`` row, not three — otherwise a single relocation would count
    as three material changes and "three material changes in 30 days" would stop
    meaning anything (ADR-0003).
    """
    emitted: list[dict[str, Any]] = []

    def _append(policy_id, version_no, endorsement_id, date, category, line,
                old_value, new_value, old_num, new_num):
        emitted.append({
            "_sort": (to_str(policy_id), date, category, line or "", version_no),
            "policy_id": to_str(policy_id),
            "endorsement_id": to_str(endorsement_id),
            "change_date": date,
            "change_category": category,
            "coverage_line": line,
            "old_value": to_str(old_value),
            "new_value": to_str(new_value),
            "old_value_num": old_num,
            "new_value_num": new_num,
        })

    for policy_id, versions in _group_by(records(policy_history), "policy_id").items():
        versions = sorted(versions, key=lambda r: int(r.get("version_no") or 0))
        for previous, current in zip(versions, versions[1:]):
            date = to_date(current.get("effective_from"))
            if date is None:
                continue
            seen_categories: set[str] = set()
            for column, category, numeric in _HISTORY_FIELD_CATEGORIES:
                old, new = previous.get(column), current.get(column)
                if to_str(old) == to_str(new):
                    continue
                if category in seen_categories:
                    continue  # one row per category per version transition
                seen_categories.add(category)
                _append(
                    policy_id, current.get("version_no"), current.get("endorsement_id"),
                    date, category, None, old, new,
                    to_num(old) if numeric else None,
                    to_num(new) if numeric else None,
                )

    for key, versions in _group_by(records(policy_coverage_history), "policy_id").items():
        by_line = _group_by(versions, "coverage_line")
        for line, line_versions in by_line.items():
            line_versions = sorted(line_versions, key=lambda r: int(r.get("version_no") or 0))
            for previous, current in zip(line_versions, line_versions[1:]):
                date = to_date(current.get("effective_from"))
                if date is None:
                    continue
                for column, category in (("limit_amount", "coverage"),
                                         ("deductible_amount", "deductible")):
                    old, new = to_num(previous.get(column)), to_num(current.get(column))
                    if old == new:
                        continue
                    if category == "deductible" and to_str(line) not in DEDUCTIBLE_LINES:
                        # E12: a deductible row on BI/PD/UMUIM is not a valid row.
                        continue
                    _append(
                        key, current.get("version_no"), current.get("endorsement_id"),
                        date, category, to_str(line),
                        None if old is None else f"{old:g}",
                        None if new is None else f"{new:g}",
                        old, new,
                    )

    emitted.sort(key=lambda r: r["_sort"])
    for index, row in enumerate(emitted, start=1):
        # Sequential over a deterministic sort, not a hash: at ~95k change events
        # an 8-digit hash space collides dozens of times by the birthday bound,
        # and the identifier contract fixes the width at eight digits (spec 01 §2).
        row["change_event_id"] = f"CHG-{index:08d}"
        del row["_sort"]

    columns = ["change_event_id", "policy_id", "endorsement_id", "change_date",
               "change_category", "coverage_line", "old_value", "new_value",
               "old_value_num", "new_value_num"]
    return pd.DataFrame(emitted, columns=columns)


# ---------------------------------------------------------------------------
# 1. policy_change_event  (spec 02 §2)
# ---------------------------------------------------------------------------

def _prior_material_counts(
    material_dates: Sequence[_dt.date],
    anchor: _dt.date,
    windows: Sequence[int],
    inclusive_of_anchor: bool,
) -> dict[int, int]:
    """Count material changes in each ``[anchor - N, anchor]`` window.

    ``inclusive_of_anchor`` distinguishes the two anchors the spec uses:

    * change grain — strictly before ``change_date``. A change cannot precede
      itself, and counting co-committed siblings would make one endorsement of
      three deltas report two prior changes on every row (ADR-0003).
    * claim grain — inclusive of ``loss_date``, because ADR-0004 rules that a
      change dated the same day as the loss is *before* the loss.
    """
    out: dict[int, int] = {}
    for window in windows:
        low = anchor - _dt.timedelta(days=window)
        out[window] = sum(
            1 for d in material_dates
            if d is not None and low <= d and (d <= anchor if inclusive_of_anchor else d < anchor)
        )
    return out


def _link_claim(
    change_date: _dt.date,
    policy_claims: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """The Linked Claim: first claim on the policy **reported** at or after the change.

    ADR-0004. Not the next claim by loss date — that anchoring cannot express a
    change made after the loss but before the insurer was told of it.

    AMBIGUITY: the specs do not define a tie-break when two claims share a report
    date. ``claim_id`` ascending is used, which is stable across regenerations
    because identifiers derive from the seed alone (ADR-0006).
    """
    candidates = [
        c for c in policy_claims
        if to_date(c.get("report_date")) is not None
        and to_date(c.get("report_date")) >= change_date
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda c: (to_date(c.get("report_date")), to_str(c.get("claim_id"))))


def _nearest_category_offsets(
    row: Mapping[str, Any],
    policy_changes: Sequence[Mapping[str, Any]],
) -> dict[str, int | None]:
    """Signed nearest-category offsets (spec 02 §2, "Category proximity").

    Negative when that category's change came *before* this row's event, positive
    when after, so symmetric co-occurrence is ``ABS(...) <= N`` with no ``OR``.

    On a row of the **same** category the offset refers to the previous distinct
    change of that category, which is what makes repeat-changer questions work.
    """
    this_date = to_date(row.get("change_date"))
    this_id = to_str(row.get("change_event_id"))
    this_category = to_str(row.get("change_category"))
    offsets: dict[str, int | None] = {}

    for category in MATERIAL_CATEGORIES:
        column = f"nearest_{category}_change_offset_days"
        peers = [
            c for c in policy_changes
            if to_str(c.get("change_category")) == category
            and to_str(c.get("change_event_id")) != this_id
            and to_date(c.get("change_date")) is not None
        ]
        if not peers:
            offsets[column] = None
            continue

        if category == this_category:
            # Previous distinct change of this category, in (date, id) order.
            earlier = [
                c for c in peers
                if (to_date(c.get("change_date")), to_str(c.get("change_event_id")))
                < (this_date, this_id)
            ]
            if not earlier:
                offsets[column] = None
                continue
            chosen = max(
                earlier,
                key=lambda c: (to_date(c.get("change_date")), to_str(c.get("change_event_id"))),
            )
        else:
            # AMBIGUITY: no tie-break is specified when a before and an after
            # change are equidistant. Smallest absolute offset wins; ties go to
            # the earlier change, then to the lower change_event_id — stable
            # across regenerations.
            chosen = min(
                peers,
                key=lambda c: (
                    abs(days_between(to_date(c.get("change_date")), this_date)),
                    days_between(to_date(c.get("change_date")), this_date),
                    to_str(c.get("change_event_id")),
                ),
            )
        offsets[column] = days_between(to_date(chosen.get("change_date")), this_date)
    return offsets


def build_policy_change_event(
    changes: Any,
    claims: Any,
    policy_history: Any,
    anchor_date: Any = None,
) -> pd.DataFrame:
    """One row per field change on a policy, material or otherwise (spec 02 §2).

    ``changes`` is the raw change grain: ``change_event_id``, ``policy_id``,
    ``endorsement_id``, ``change_date``, ``change_category``, ``coverage_line``,
    ``old_value``, ``new_value``, ``old_value_num``, ``new_value_num``
    (see :func:`derive_change_events_from_scd2`).
    """
    change_rows = records(changes)
    claim_rows = records(claims)
    history_rows = records(policy_history)

    claims_by_policy = _group_by(claim_rows, "policy_id")
    changes_by_policy = _group_by(change_rows, "policy_id")
    history_by_policy = _group_by(history_rows, "policy_id")
    customer_of = _policy_customer_map(history_rows)
    start_of = _policy_start_dates(history_rows)

    out: list[dict[str, Any]] = []
    for policy_id, policy_changes in changes_by_policy.items():
        policy_id = to_str(policy_id)
        policy_claims = claims_by_policy.get(policy_id, [])
        versions = sorted(
            history_by_policy.get(policy_id, []),
            key=lambda r: int(r.get("version_no") or 0),
        )
        material_dates = sorted(
            to_date(c.get("change_date")) for c in policy_changes
            if is_material_category(c.get("change_category"))
            and to_date(c.get("change_date")) is not None
        )

        for source in policy_changes:
            category = to_str(source.get("change_category"))
            date = to_date(source.get("change_date"))
            old_num = to_num(source.get("old_value_num"))
            new_num = to_num(source.get("new_value_num"))
            if category in CATEGORICAL_CATEGORIES:
                # E3: the numeric pair is NULL exactly for categorical categories.
                old_num = new_num = None

            row: dict[str, Any] = {
                "change_event_id": to_str(source.get("change_event_id")),
                "policy_id": policy_id,
                "customer_id": to_str(source.get("customer_id")) or customer_of.get(policy_id),
                "endorsement_id": to_str(source.get("endorsement_id")),
                "change_date": date,
                "change_category": category,
                "is_material": is_material_category(category),
                "coverage_line": to_str(source.get("coverage_line")),
                "old_value": to_str(source.get("old_value")),
                "new_value": to_str(source.get("new_value")),
                "old_value_num": old_num,
                "new_value_num": new_num,
                "change_direction": change_direction(category, old_num, new_num),
                "change_pct": change_pct(category, old_num, new_num),
                "policy_start_date": start_of.get(policy_id),
                "policy_state": None,
            }

            if date is not None and versions:
                version = _scd_lookup(versions, date)
                if version is not None:
                    row["policy_state"] = to_str(version.get("garaging_state"))

            # --- Claim linkage (ADR-0004) -----------------------------------
            linked = _link_claim(date, policy_claims) if date is not None else None
            if linked is None:
                # NULL propagates together. change_timing must never default to
                # 'before_loss' on an unlinked row, or that filter stops meaning
                # "linked and before the loss" (E4).
                for column in LINKAGE_COLUMNS:
                    row[column] = None
                row["change_relates_to_claimed_coverage"] = None
            else:
                loss_date = to_date(linked.get("loss_date"))
                report_date = to_date(linked.get("report_date"))
                amount = to_num(linked.get("settled_amount"))
                claim_line = to_str(linked.get("coverage_line"))
                days_loss = days_between(loss_date, date)
                row["next_claim_id"] = to_str(linked.get("claim_id"))
                # Positive: the change preceded the loss.
                # Negative: the change fell inside the Loss-to-Report Gap.
                row["days_to_next_claim_loss"] = days_loss
                row["days_to_next_claim_report"] = days_between(report_date, date)
                row["change_timing"] = change_timing(days_loss)
                row["next_claim_amount"] = amount
                row["next_claim_severity"] = severity_band(amount)
                row["next_claim_coverage_line"] = claim_line
                # AMBIGUITY: SQL equality would return NULL when the change is
                # not line-specific. False is used instead — an address change
                # cannot relate to the claimed coverage — so the column is a
                # usable two-valued filter on every linked row.
                row["change_relates_to_claimed_coverage"] = (
                    row["coverage_line"] is not None and row["coverage_line"] == claim_line
                )

            # --- Category proximity ----------------------------------------
            row.update(_nearest_category_offsets(row, policy_changes))

            # --- Context ----------------------------------------------------
            if date is not None:
                counts = _prior_material_counts(
                    material_dates, date, (30, 60, 90), inclusive_of_anchor=False
                )
            else:  # pragma: no cover - defensive
                counts = {30: 0, 60: 0, 90: 0}
            row["material_changes_prior_30d"] = counts[30]
            row["material_changes_prior_60d"] = counts[60]
            row["material_changes_prior_90d"] = counts[90]

            out.append(row)

    out.sort(key=lambda r: (r["policy_id"], r["change_date"] or _dt.date.min,
                            r["change_event_id"] or ""))
    return frame(out, POLICY_CHANGE_EVENT_SCHEMA)


# ---------------------------------------------------------------------------
# 2. claim_event  (spec 02 §3)
# ---------------------------------------------------------------------------

def build_claim_event(
    claims: Any,
    changes: Any,
    policy_coverage_history: Any,
    policy_history: Any,
    anchor_date: Any = None,
) -> pd.DataFrame:
    """One row per claim. **The table for claim-level counting** (spec 02 §3).

    Every prior-change window here is anchored on ``loss_date``, matching product
    language (ADR-0004), unlike the change table which is anchored on the change.
    """
    claim_rows = records(claims)
    change_rows = records(changes)
    coverage_rows = records(policy_coverage_history)
    customer_of = _policy_customer_map(policy_history)

    changes_by_policy = _group_by(change_rows, "policy_id")
    coverage_by_policy = _group_by(coverage_rows, "policy_id")

    out: list[dict[str, Any]] = []
    for source in claim_rows:
        policy_id = to_str(source.get("policy_id"))
        loss_date = to_date(source.get("loss_date"))
        report_date = to_date(source.get("report_date"))
        amount = to_num(source.get("settled_amount"))
        claim_line = to_str(source.get("coverage_line"))

        policy_changes = changes_by_policy.get(policy_id, [])
        material = [
            c for c in policy_changes
            if is_material_category(c.get("change_category"))
            and to_date(c.get("change_date")) is not None
        ]

        # applicable_limit: the limit on this line at the loss date.
        limit = None
        line_versions = [
            v for v in coverage_by_policy.get(policy_id, [])
            if to_str(v.get("coverage_line")) == claim_line
        ]
        if loss_date is not None and line_versions:
            version = _scd_lookup(
                sorted(line_versions, key=lambda r: int(r.get("version_no") or 0)), loss_date
            )
            if version is not None:
                limit = to_num(version.get("limit_amount"))

        utilization = limit_utilization_pct(amount, limit)

        row: dict[str, Any] = {
            "claim_id": to_str(source.get("claim_id")),
            "policy_id": policy_id,
            "customer_id": to_str(source.get("customer_id")) or customer_of.get(policy_id),
            "coverage_line": claim_line,
            "loss_date": loss_date,
            "report_date": report_date,
            "loss_to_report_days": (
                days_between(report_date, loss_date)
                if loss_date is not None and report_date is not None else None
            ),
            "settled_amount": amount,
            "severity_band": severity_band(amount),
            "applicable_limit": limit,
            "limit_utilization_pct": utilization,
            # NULL, not False, when utilisation is unknown: no-sentinel rule.
            "at_or_near_limit": (
                None if utilization is None else utilization >= AT_OR_NEAR_LIMIT_PCT
            ),
            "claim_status": to_str(source.get("claim_status")),
        }

        material_dates = sorted(to_date(c.get("change_date")) for c in material)
        counts = _prior_material_counts(
            material_dates, loss_date, (30, 60, 90), inclusive_of_anchor=True
        ) if loss_date is not None else {30: 0, 60: 0, 90: 0}
        row["material_changes_prior_30d"] = counts[30]
        row["material_changes_prior_60d"] = counts[60]
        row["material_changes_prior_90d"] = counts[90]

        # The Loss-to-Report Gap is (loss_date, report_date]: a change dated the
        # same day as the loss is before_loss, and one dated the same day as the
        # report is still inside the gap (ADR-0004 same-day ties).
        if loss_date is not None and report_date is not None:
            row["material_changes_in_loss_report_gap"] = sum(
                1 for d in material_dates if loss_date < d <= report_date
            )
        else:  # pragma: no cover - defensive
            row["material_changes_in_loss_report_gap"] = 0

        # Last material change at or before the loss.
        before_loss = [
            c for c in material if to_date(c.get("change_date")) <= loss_date
        ] if loss_date is not None else []
        if before_loss:
            last = max(
                before_loss,
                key=lambda c: (to_date(c.get("change_date")), to_str(c.get("change_event_id")) or ""),
            )
            last_date = to_date(last.get("change_date"))
            row["days_since_last_material_change_before_loss"] = days_between(loss_date, last_date)
            row["last_material_change_category"] = to_str(last.get("change_category"))
            row["last_material_change_date"] = last_date
        else:
            row["days_since_last_material_change_before_loss"] = None
            row["last_material_change_category"] = None
            row["last_material_change_date"] = None

        # Relevant Change (CONTEXT.md): a coverage *or deductible* change on the
        # same Coverage Line the claim was later filed against.
        if loss_date is not None:
            window_start = loss_date - _dt.timedelta(days=60)
            row["relevant_coverage_change_prior_60d"] = any(
                to_str(c.get("change_category")) in ("coverage", "deductible")
                and to_str(c.get("coverage_line")) == claim_line
                and window_start <= to_date(c.get("change_date")) <= loss_date
                for c in material
            )
        else:  # pragma: no cover - defensive
            row["relevant_coverage_change_prior_60d"] = False

        out.append(row)

    out.sort(key=lambda r: (r["policy_id"] or "", r["claim_id"] or ""))
    return frame(out, CLAIM_EVENT_SCHEMA)


# ---------------------------------------------------------------------------
# 3. policy_pattern_match  (spec 02 §6, ADR-0009) — the single rule pass
# ---------------------------------------------------------------------------

def _densest_window(dates: Sequence[_dt.date], span_days: int) -> tuple[int, int, int]:
    """``(count, start_index, end_index)`` of the densest ``span_days`` window."""
    best = (0, 0, 0)
    for i, start in enumerate(dates):
        j = i
        while j + 1 < len(dates) and days_between(dates[j + 1], start) <= span_days:
            j += 1
        count = j - i + 1
        if count > best[0]:
            best = (count, i, j)
    return best


def build_policy_pattern_match(change_event: Any, claim_event: Any) -> pd.DataFrame:
    """One row per policy × matched pattern (ADR-0009).

    **This is the single rule evaluation pass.** :func:`build_policy_profile`
    derives the six booleans and ``noteworthy_pattern_count`` from these rows and
    never re-evaluates a predicate — ADR-0007 puts the generated SQL in the
    evidence panel, so a disagreement would be visible on screen (E13, E14).

    Grain is policy × pattern, so each rule contributes at most one row per
    policy. AMBIGUITY: the specs do not say which occurrence is kept when a rule
    fires more than once. The **most recent** one is kept — that is what an
    investigator opening the evidence panel wants to see.
    """
    changes = records(change_event)
    claims = records(claim_event)
    changes_by_policy = _group_by(changes, "policy_id")
    claims_by_policy = _group_by(claims, "policy_id")
    policies = sorted({*changes_by_policy, *claims_by_policy}, key=lambda p: to_str(p) or "")

    def _latest(rows, date_key):
        return max(rows, key=lambda r: (
            to_date(r.get(date_key)),
            to_str(r.get("change_event_id")) or to_str(r.get("claim_id")) or "",
        ))

    def _line_name(line):
        return LINE_NAMES.get(to_str(line) or "", to_str(line) or "the coverage line")

    out: list[dict[str, Any]] = []
    for policy_id in policies:
        policy_id = to_str(policy_id)
        policy_changes = changes_by_policy.get(policy_id, [])
        policy_claims = claims_by_policy.get(policy_id, [])
        matches: list[dict[str, Any]] = []

        def emit(code, matched_on, change_id, claim_id, summary):
            matches.append({
                "policy_id": policy_id,
                "pattern_code": code,
                "pattern_name": PATTERN_NAMES[code],
                "matched_on_date": matched_on,
                "evidence_change_event_id": change_id,
                "evidence_claim_id": claim_id,
                "evidence_summary": summary,
            })

        # R1 — coverage increase, Linked Claim on the same Coverage Line within
        #      60 days, before_loss.
        hits = [
            c for c in policy_changes
            if to_str(c.get("change_category")) == "coverage"
            and to_str(c.get("change_direction")) == "increase"
            and to_str(c.get("change_timing")) == "before_loss"
            and bool(c.get("change_relates_to_claimed_coverage"))
            and to_num(c.get("days_to_next_claim_loss")) is not None
            and to_num(c.get("days_to_next_claim_loss")) <= PATTERN_CLAIM_WINDOW_DAYS
        ]
        if hits:
            hit = _latest(hits, "change_date")
            emit(
                "coverage_raised_then_claimed_same_line",
                to_date(hit.get("change_date")),
                to_str(hit.get("change_event_id")),
                to_str(hit.get("next_claim_id")),
                f"{_line_name(hit.get('coverage_line'))} limit increased, and claim "
                f"{to_str(hit.get('next_claim_id'))} on the same line occurred "
                f"{int(to_num(hit.get('days_to_next_claim_loss')))} days later.",
            )

        # R2 — deductible decrease, Linked Claim within 60 days, before_loss.
        hits = [
            c for c in policy_changes
            if to_str(c.get("change_category")) == "deductible"
            and to_str(c.get("change_direction")) == "decrease"
            and to_str(c.get("change_timing")) == "before_loss"
            and to_num(c.get("days_to_next_claim_loss")) is not None
            and to_num(c.get("days_to_next_claim_loss")) <= PATTERN_CLAIM_WINDOW_DAYS
        ]
        if hits:
            hit = _latest(hits, "change_date")
            emit(
                "deductible_lowered_before_claim",
                to_date(hit.get("change_date")),
                to_str(hit.get("change_event_id")),
                to_str(hit.get("next_claim_id")),
                f"{_line_name(hit.get('coverage_line'))} deductible lowered "
                f"{int(to_num(hit.get('days_to_next_claim_loss')))} days before the loss on claim "
                f"{to_str(hit.get('next_claim_id'))}.",
            )

        # R3 — any material change with change_timing = 'after_loss_before_report'.
        hits = [
            c for c in policy_changes
            if bool(c.get("is_material"))
            and to_str(c.get("change_timing")) == "after_loss_before_report"
        ]
        if hits:
            hit = _latest(hits, "change_date")
            emit(
                "change_in_loss_report_gap",
                to_date(hit.get("change_date")),
                to_str(hit.get("change_event_id")),
                to_str(hit.get("next_claim_id")),
                f"A {to_str(hit.get('change_category'))} change occurred after the loss on claim "
                f"{to_str(hit.get('next_claim_id'))} and before it was reported.",
            )

        # R4 — three or more material changes within any 30-day span.
        material = sorted(
            (c for c in policy_changes if bool(c.get("is_material"))
             and to_date(c.get("change_date")) is not None),
            key=lambda c: (to_date(c.get("change_date")), to_str(c.get("change_event_id")) or ""),
        )
        dates = [to_date(c.get("change_date")) for c in material]
        count, start_index, end_index = _densest_window(dates, PATTERN_CLUSTER_SPAN_DAYS)
        if count >= PATTERN_CLUSTER_MIN_CHANGES:
            last = material[end_index]
            emit(
                "rapid_change_cluster",
                to_date(last.get("change_date")),
                to_str(last.get("change_event_id")),
                None,
                f"{count} material changes occurred within "
                f"{days_between(dates[end_index], dates[start_index])} days.",
            )

        # R5 — a vehicle change with ABS(nearest_address_change_offset_days) <= 60.
        hits = [
            c for c in policy_changes
            if to_str(c.get("change_category")) == "vehicle"
            and to_num(c.get("nearest_address_change_offset_days")) is not None
            and abs(to_num(c.get("nearest_address_change_offset_days")))
            <= PATTERN_VEHICLE_ADDRESS_DAYS
        ]
        if hits:
            hit = _latest(hits, "change_date")
            offset = int(to_num(hit.get("nearest_address_change_offset_days")))
            emit(
                "vehicle_and_address_within_60d",
                to_date(hit.get("change_date")),
                to_str(hit.get("change_event_id")),
                None,
                f"A vehicle change was observed alongside an address change "
                f"{abs(offset)} days {'earlier' if offset < 0 else 'later'}.",
            )

        # R6 — an at_or_near_limit claim where that line's limit rose within the
        #      prior 90 days.
        increases = [
            c for c in policy_changes
            if to_str(c.get("change_category")) == "coverage"
            and to_str(c.get("change_direction")) == "increase"
            and to_date(c.get("change_date")) is not None
        ]
        hits = []
        for claim in policy_claims:
            if not bool(claim.get("at_or_near_limit")):
                continue
            loss_date = to_date(claim.get("loss_date"))
            if loss_date is None:
                continue
            window_start = loss_date - _dt.timedelta(days=PATTERN_LIMIT_RAISED_WINDOW_DAYS)
            raises = [
                c for c in increases
                if to_str(c.get("coverage_line")) == to_str(claim.get("coverage_line"))
                and window_start <= to_date(c.get("change_date")) <= loss_date
            ]
            if raises:
                hits.append((claim, max(raises, key=lambda c: to_date(c.get("change_date")))))
        if hits:
            claim, raise_row = max(hits, key=lambda pair: (
                to_date(pair[0].get("loss_date")), to_str(pair[0].get("claim_id")) or ""
            ))
            emit(
                "claim_near_new_limit",
                to_date(claim.get("loss_date")),
                to_str(raise_row.get("change_event_id")),
                to_str(claim.get("claim_id")),
                f"Claim {to_str(claim.get('claim_id'))} settled at "
                f"{to_num(claim.get('limit_utilization_pct')):.0f}% of the "
                f"{_line_name(claim.get('coverage_line'))} limit, which was raised "
                f"{days_between(to_date(claim.get('loss_date')), to_date(raise_row.get('change_date')))}"
                f" days earlier.",
            )

        matches.sort(key=lambda m: PATTERN_CODES.index(m["pattern_code"]))
        out.extend(matches)

    return frame(out, POLICY_PATTERN_MATCH_SCHEMA)


# ---------------------------------------------------------------------------
# 4. policy_profile  (spec 02 §4)
# ---------------------------------------------------------------------------

def _tenure_years(policy_start: _dt.date | None, anchor: _dt.date) -> float:
    if policy_start is None:
        return 1.0
    days = max(days_between(anchor, policy_start), 1)
    return days / 365.25


def build_policy_profile(
    policy_history: Any,
    policy_coverage_history: Any,
    change_event: Any,
    claim_event: Any,
    pattern_match: Any,
    anchor_date: Any,
) -> pd.DataFrame:
    """One row per policy (spec 02 §4).

    **Recency is stored as dates, never as day-counts (E20, ADR-0006).** An
    event-to-now delta computed here would be anchored to ``anchor_date`` and
    silently disagree with ``CURRENT_DATE`` arithmetic by exactly the staleness
    gap. "Recent" is computed at query time from ``last_material_change_date``
    and ``last_claim_date``, defaulting to 90 days.

    ``material_changes_per_year`` and ``claims_per_year`` are rates over tenure,
    not event-to-now deltas: they answer "how often", not "how long ago", and
    ADR-0010 requires them rate-normalised so tenure does not dominate similarity.
    """
    anchor = to_date(anchor_date)
    history_by_policy = _group_by(records(policy_history), "policy_id")
    coverage_by_policy = _group_by(records(policy_coverage_history), "policy_id")
    changes_by_policy = _group_by(records(change_event), "policy_id")
    claims_by_policy = _group_by(records(claim_event), "policy_id")
    matches_by_policy = _group_by(records(pattern_match), "policy_id")
    start_of = _policy_start_dates(records(policy_history))

    out: list[dict[str, Any]] = []
    for policy_id in sorted(history_by_policy, key=lambda p: to_str(p) or ""):
        policy_id = to_str(policy_id)
        versions = history_by_policy[policy_id]
        current = _current_version(versions) or {}
        coverage_current = {
            to_str(v.get("coverage_line")): v
            for v in coverage_by_policy.get(policy_id, [])
            if bool(v.get("is_current"))
        }
        policy_changes = changes_by_policy.get(policy_id, [])
        policy_claims = claims_by_policy.get(policy_id, [])
        matches = matches_by_policy.get(policy_id, [])

        material = [c for c in policy_changes if bool(c.get("is_material"))]
        material_dates = sorted(
            d for d in (to_date(c.get("change_date")) for c in material) if d is not None
        )
        start_date = start_of.get(policy_id)
        tenure = _tenure_years(start_date, anchor)

        def _limit(line):
            return to_num((coverage_current.get(line) or {}).get("limit_amount"))

        def _deductible(line):
            return to_num((coverage_current.get(line) or {}).get("deductible_amount"))

        category_counts = {
            category: sum(
                1 for c in material if to_str(c.get("change_category")) == category
            )
            for category in MATERIAL_CATEGORIES
        }

        increases = sum(
            1 for c in policy_changes
            if to_str(c.get("change_category")) == "coverage"
            and to_str(c.get("change_direction")) == "increase"
        )
        decreases = sum(
            1 for c in policy_changes
            if to_str(c.get("change_category")) == "coverage"
            and to_str(c.get("change_direction")) == "decrease"
        )
        # AMBIGUITY: spec 02 §4 names the column but not its type. A string keeps
        # it Genie-filterable in the same vocabulary as change_direction; the
        # numeric bias ADR-0010's feature vector needs is recomputed in
        # build_policy_similarity from the same counts.
        if increases == decreases == 0:
            net_direction = "none"
        elif increases > decreases:
            net_direction = "increase"
        elif decreases > increases:
            net_direction = "decrease"
        else:
            net_direction = "net_zero"

        peak_30d = _densest_window(material_dates, PATTERN_CLUSTER_SPAN_DAYS)[0]

        severities = [
            to_str(c.get("severity_band")) for c in policy_claims
            if to_str(c.get("severity_band")) is not None
        ]
        max_severity = (
            max(severities, key=lambda b: SEVERITY_ORDINAL[b]) if severities else None
        )
        utilizations = [
            to_num(c.get("limit_utilization_pct")) for c in policy_claims
            if to_num(c.get("limit_utilization_pct")) is not None
        ]
        loss_dates = [
            to_date(c.get("loss_date")) for c in policy_claims
            if to_date(c.get("loss_date")) is not None
        ]

        if material_dates and loss_dates:
            within = sum(
                1 for d in material_dates
                if any(loss - _dt.timedelta(days=60) <= d <= loss for loss in loss_dates)
            )
            share_within_60d = round(within / len(material_dates), 6)
        elif material_dates:
            share_within_60d = 0.0
        else:
            share_within_60d = None

        matched_codes = {to_str(m.get("pattern_code")) for m in matches}

        row: dict[str, Any] = {
            "policy_id": policy_id,
            "customer_id": to_str(current.get("customer_id")),
            "policy_status": to_str(current.get("policy_status")),
            "policy_start_date": start_date,
            "term_start_date": to_date(current.get("term_start_date")),
            "term_end_date": to_date(current.get("term_end_date")),
            "current_city": to_str(current.get("garaging_city")),
            "current_state": to_str(current.get("garaging_state")),
            "current_annual_premium": to_num(current.get("annual_premium")),
            "current_primary_vehicle": to_str(current.get("primary_vehicle_id")),
            "current_coll_limit": _limit("COLL"),
            "current_comp_limit": _limit("COMP"),
            "current_bi_limit": _limit("BI"),
            "current_coll_deductible": _deductible("COLL"),
            "current_comp_deductible": _deductible("COMP"),
            "material_change_count": len(material),
            "material_changes_per_year": round(len(material) / tenure, 6),
            "peak_material_changes_30d": peak_30d,
            "coverage_change_count": category_counts["coverage"],
            "deductible_change_count": category_counts["deductible"],
            "vehicle_change_count": category_counts["vehicle"],
            "address_change_count": category_counts["address"],
            "status_change_count": category_counts["status"],
            "net_coverage_direction": net_direction,
            "claim_count": len(policy_claims),
            "claims_per_year": round(len(policy_claims) / tenure, 6),
            "max_severity_band": max_severity,
            "mean_limit_utilization": (
                round(sum(utilizations) / len(utilizations), 6) if utilizations else None
            ),
            "share_material_changes_within_60d_before_loss": share_within_60d,
            # Recency — dates only.
            "last_material_change_date": max(material_dates) if material_dates else None,
            # AMBIGUITY: "last claim" is dated by loss_date; CONTEXT.md makes Loss
            # Date the default anchor for product language about timing.
            "last_claim_date": max(loss_dates) if loss_dates else None,
            # Derived from the single pattern pass — never a second predicate.
            "noteworthy_pattern_count": len(matched_codes),
        }
        for code in PATTERN_CODES:
            row[f"pattern_{code}"] = code in matched_codes

        out.append(row)

    return frame(out, POLICY_PROFILE_SCHEMA)


# ---------------------------------------------------------------------------
# 5. policy_timeline_event  (spec 02 §5)
# ---------------------------------------------------------------------------

def _change_display_label(row: Mapping[str, Any]) -> str:
    category = to_str(row.get("change_category"))
    direction = to_str(row.get("change_direction"))
    line = LINE_NAMES.get(to_str(row.get("coverage_line")) or "", None)
    moved = "increased" if direction == "increase" else "decreased"
    if category == "coverage":
        return f"{line or 'Coverage'} limit {moved}"
    if category == "deductible":
        return f"{line or 'Coverage'} deductible {moved}"
    if category == "vehicle":
        return "Primary vehicle changed"
    if category == "address":
        return "Garaging address changed"
    if category == "status":
        return f"Policy status changed to {to_str(row.get('new_value')) or 'a new status'}"
    if category == "premium":
        return f"Annual premium {moved}"
    if category == "agent":
        return "Agent changed"
    return "Policy changed"  # pragma: no cover - defensive


def build_policy_timeline_event(
    changes: Any,
    claims: Any,
    claim_payment: Any,
    policy_history: Any,
    anchor_date: Any = None,
) -> pd.DataFrame:
    """One row per dated thing that happened to a policy (spec 02 §5).

    **For reading one policy's story. Never for counting** — it mixes grains.

    AMBIGUITY: the ``event_type`` enum has one claim value, ``claim_filed``, but a
    claim carries two dates. It is placed on ``report_date`` — filing *is*
    reporting, it matches ADR-0004's report-date anchoring, and it is the only
    placement under which a change inside the Loss-to-Report Gap renders *before*
    the claim marker, which is the story scenario S3 exists to show. The loss date
    and the gap are carried in ``display_label``.
    """
    change_rows = records(changes)
    claim_rows = records(claims)
    payment_rows = records(claim_payment)
    history_rows = records(policy_history)
    start_of = _policy_start_dates(history_rows)
    claim_policy = {
        to_str(c.get("claim_id")): to_str(c.get("policy_id")) for c in claim_rows
    }
    claim_line = {
        to_str(c.get("claim_id")): to_str(c.get("coverage_line")) for c in claim_rows
    }

    out: list[dict[str, Any]] = []

    def _blank(**kwargs) -> dict[str, Any]:
        row = {name: None for name, _ in POLICY_TIMELINE_EVENT_SCHEMA}
        row["is_material"] = False
        row.update(kwargs)
        return row

    # policy_created
    for policy_id, start_date in start_of.items():
        if start_date is None:
            continue
        out.append(_blank(
            timeline_event_id=f"TLE-N-{_policy_token(policy_id)}",
            policy_id=policy_id,
            event_date=start_date,
            event_type="policy_created",
            display_label="Policy created",
            # This source_id *is* a policy id, which E19 explicitly permits.
            source_id=policy_id,
        ))

    # renewal — a new term starting, never a Policy Change (spec 01 §6 rule 2)
    for policy_id, versions in _group_by(history_rows, "policy_id").items():
        versions = sorted(versions, key=lambda r: int(r.get("version_no") or 0))
        seen: set[_dt.date] = set()
        previous_term = None
        for version in versions:
            term_start = to_date(version.get("term_start_date"))
            if term_start is None:
                continue
            if previous_term is not None and term_start > previous_term and term_start not in seen:
                seen.add(term_start)
                out.append(_blank(
                    timeline_event_id=(
                        f"TLE-R-{_policy_token(to_str(policy_id))}-{term_start.isoformat()}"
                    ),
                    policy_id=to_str(policy_id),
                    event_date=term_start,
                    event_type="renewal",
                    display_label="Policy renewed",
                    source_id=None,
                ))
            previous_term = term_start if previous_term is None else max(previous_term, term_start)

    # policy_change / status_change
    for source in change_rows:
        category = to_str(source.get("change_category"))
        direction = to_str(source.get("change_direction")) or change_direction(
            category, source.get("old_value_num"), source.get("new_value_num")
        )
        enriched = dict(source)
        enriched["change_direction"] = direction
        out.append(_blank(
            timeline_event_id=f"TLE-C-{to_str(source.get('change_event_id'))}",
            policy_id=to_str(source.get("policy_id")),
            event_date=to_date(source.get("change_date")),
            # The enum carries both values; a status change takes the specific one.
            event_type="status_change" if category == "status" else "policy_change",
            event_category=category,
            endorsement_id=to_str(source.get("endorsement_id")),
            coverage_line=to_str(source.get("coverage_line")),
            old_value=to_str(source.get("old_value")),
            new_value=to_str(source.get("new_value")),
            display_label=_change_display_label(enriched),
            amount=None,  # spec 02 §5: amount is a claim or payment amount
            is_material=is_material_category(category),
            source_id=to_str(source.get("change_event_id")),
        ))

    # claim_filed
    for source in claim_rows:
        loss_date = to_date(source.get("loss_date"))
        report_date = to_date(source.get("report_date"))
        line = to_str(source.get("coverage_line"))
        gap = (
            days_between(report_date, loss_date)
            if loss_date is not None and report_date is not None else None
        )
        name = LINE_NAMES.get(line or "", "Claim")
        if gap is None:
            label = f"{name} claim reported"
        elif gap == 0:
            label = f"{name} claim reported the same day as the loss"
        else:
            label = f"{name} claim reported {gap} days after the loss"
        out.append(_blank(
            timeline_event_id=f"TLE-K-{to_str(source.get('claim_id'))}",
            policy_id=to_str(source.get("policy_id")),
            event_date=report_date,
            event_type="claim_filed",
            coverage_line=line,
            display_label=label,
            amount=to_num(source.get("settled_amount")),
            source_id=to_str(source.get("claim_id")),
        ))

    # claim_payment
    for source in payment_rows:
        claim_id = to_str(source.get("claim_id"))
        out.append(_blank(
            timeline_event_id=f"TLE-Y-{to_str(source.get('payment_id'))}",
            policy_id=claim_policy.get(claim_id),
            event_date=to_date(source.get("payment_date")),
            event_type="claim_payment",
            coverage_line=claim_line.get(claim_id),
            display_label="Claim payment",
            amount=to_num(source.get("amount")),
            # spec 02 §5: source_id is a change_event_id or a claim_id, so a
            # payment points at its claim and the UI can group the two.
            source_id=claim_id,
        ))

    out.sort(key=lambda r: (
        r["policy_id"] or "",
        r["event_date"] or _dt.date.min,
        TIMELINE_EVENT_TYPES.index(r["event_type"]),
        r["timeline_event_id"] or "",
    ))
    return frame(out, POLICY_TIMELINE_EVENT_SCHEMA)


# ---------------------------------------------------------------------------
# 6. policy_similarity  (spec 02 §7, ADR-0010)
# ---------------------------------------------------------------------------

#: The named feature dimensions of ADR-0010, in order. ``label`` is the phrase
#: ``top_reasons`` uses; it is bound by the vocabulary rule (E18).
SIMILARITY_FEATURES: tuple[tuple[str, str], ...] = (
    ("material_changes_per_year", "a similar material change rate"),
    ("peak_material_changes_30d", "a similar peak change density"),
    ("share_coverage", "a similar share of coverage changes"),
    ("share_deductible", "a similar share of deductible changes"),
    ("share_vehicle", "a similar share of vehicle changes"),
    ("share_address", "a similar share of address changes"),
    ("share_status", "a similar share of status changes"),
    ("net_coverage_bias", "a similar net coverage direction"),
    ("claims_per_year", "a similar claim rate"),
    ("max_severity_ordinal", "a similar maximum severity band"),
    ("mean_limit_utilization", "a similar mean limit utilisation"),
    ("share_within_60d_before_loss", "a similar share of changes before a loss"),
)

#: Named dimensions are reported only when the pair is genuinely close on them.
TOP_REASON_Z_THRESHOLD: float = 0.5
TOP_REASON_LIMIT: int = 3


def _similarity_feature_vector(
    profile_row: Mapping[str, Any],
    coverage_increases: int,
    coverage_decreases: int,
) -> dict[str, float]:
    material_count = int(to_num(profile_row.get("material_change_count")) or 0)

    def _share(column: str) -> float:
        if material_count == 0:
            return 0.0
        return (to_num(profile_row.get(column)) or 0.0) / material_count

    coverage_changes = coverage_increases + coverage_decreases
    return {
        "material_changes_per_year": to_num(profile_row.get("material_changes_per_year")) or 0.0,
        "peak_material_changes_30d": to_num(profile_row.get("peak_material_changes_30d")) or 0.0,
        "share_coverage": _share("coverage_change_count"),
        "share_deductible": _share("deductible_change_count"),
        "share_vehicle": _share("vehicle_change_count"),
        "share_address": _share("address_change_count"),
        "share_status": _share("status_change_count"),
        # Rate-normalised bias in [-1, 1] rather than a raw count, so tenure and
        # change volume do not re-enter through this dimension (ADR-0010).
        "net_coverage_bias": (
            0.0 if coverage_changes == 0
            else (coverage_increases - coverage_decreases) / coverage_changes
        ),
        "claims_per_year": to_num(profile_row.get("claims_per_year")) or 0.0,
        "max_severity_ordinal": float(
            SEVERITY_ORDINAL.get(to_str(profile_row.get("max_severity_band")) or "", 0)
        ),
        "mean_limit_utilization": to_num(profile_row.get("mean_limit_utilization")) or 0.0,
        "share_within_60d_before_loss": to_num(
            profile_row.get("share_material_changes_within_60d_before_loss")
        ) or 0.0,
    }


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Overlap of two pattern-code sets. Two policies with no patterns at all are
    identical on this dimension, so the empty/empty case is 1.0."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def build_policy_similarity(
    policy_profile: Any,
    change_event: Any,
    pattern_match: Any,
    k: int = K_NEIGHBOURS,
) -> pd.DataFrame:
    """Top-K neighbours per policy, exact brute force (ADR-0010).

    Not approximate nearest neighbour: demo reproducibility depends on identical
    top-K ordering across regenerations and ANN gives no such guarantee under
    ties. Ordered by ``similarity_score DESC`` then ``similar_policy_id ASC``
    (E16); a policy is never its own neighbour (E15). Directional by design — A
    appearing in B's top 20 does not imply the reverse.
    """
    profiles = records(policy_profile)
    changes = records(change_event)
    matches = records(pattern_match)

    coverage_direction_counts: dict[str, list[int]] = {}
    for row in changes:
        if to_str(row.get("change_category")) != "coverage":
            continue
        counts = coverage_direction_counts.setdefault(to_str(row.get("policy_id")), [0, 0])
        direction = to_str(row.get("change_direction"))
        if direction == "increase":
            counts[0] += 1
        elif direction == "decrease":
            counts[1] += 1

    pattern_sets: dict[str, frozenset[str]] = {}
    for policy_id, rows in _group_by(matches, "policy_id").items():
        pattern_sets[to_str(policy_id)] = frozenset(
            to_str(r.get("pattern_code")) for r in rows
        )

    policy_ids = [to_str(p.get("policy_id")) for p in profiles]
    vectors: dict[str, dict[str, float]] = {}
    for profile_row in profiles:
        policy_id = to_str(profile_row.get("policy_id"))
        increases, decreases = coverage_direction_counts.get(policy_id, [0, 0])
        vectors[policy_id] = _similarity_feature_vector(profile_row, increases, decreases)

    if len(policy_ids) < 2:
        return frame([], POLICY_SIMILARITY_SCHEMA)

    # z-score each numeric dimension across the whole population. Dataset-relative
    # is harmless here: z-scores and neighbours regenerate together from the same
    # seed (ADR-0010), unlike the percentile severity bands rejected in ADR-0008.
    feature_names = [name for name, _ in SIMILARITY_FEATURES]
    stats: dict[str, tuple[float, float]] = {}
    for name in feature_names:
        values = [vectors[p][name] for p in policy_ids]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        stats[name] = (mean, std if std > 0 else 1.0)

    z: dict[str, dict[str, float]] = {
        p: {n: (vectors[p][n] - stats[n][0]) / stats[n][1] for n in feature_names}
        for p in policy_ids
    }

    out: list[dict[str, Any]] = []
    for policy_id in sorted(policy_ids):
        own_z = z[policy_id]
        own_patterns = pattern_sets.get(policy_id, frozenset())
        scored: list[tuple[float, str, float]] = []
        for other in policy_ids:
            if other == policy_id:
                continue  # E15
            other_z = z[other]
            euclidean = math.sqrt(
                sum((own_z[n] - other_z[n]) ** 2 for n in feature_names)
            )
            jaccard = _jaccard(own_patterns, pattern_sets.get(other, frozenset()))
            distance = euclidean + PATTERN_WEIGHT * (1.0 - jaccard)
            score = round(1.0 / (1.0 + distance), SIMILARITY_SCORE_DECIMALS)
            scored.append((score, other, distance))

        scored.sort(key=lambda item: (-item[0], item[1]))  # score DESC, id ASC
        for rank, (score, other, _distance) in enumerate(scored[:k], start=1):
            out.append({
                "policy_id": policy_id,
                "similar_policy_id": other,
                "rank": rank,
                "similarity_score": score,
                "top_reasons": _top_reasons(
                    own_z, z[other], own_patterns, pattern_sets.get(other, frozenset())
                ),
            })

    return frame(out, POLICY_SIMILARITY_SCHEMA)


def _top_reasons(
    own_z: Mapping[str, float],
    other_z: Mapping[str, float],
    own_patterns: frozenset[str],
    other_patterns: frozenset[str],
) -> str:
    """Named feature dimensions on which the pair is closest (ADR-0010).

    Generated at pipeline time from the named dimensions, under the approved
    vocabulary — it surfaces verbatim in the UI and in Genie's answers, so the
    enforcement point is the pipeline, not the front end (E18).
    """
    reasons: list[str] = []
    shared = sorted(own_patterns & other_patterns, key=lambda c: PATTERN_CODES.index(c))
    for code in shared[:2]:
        reasons.append(f"shares the noteworthy pattern '{PATTERN_NAMES[code]}'")

    close = sorted(
        (
            (abs(own_z[name] - other_z[name]), label)
            for name, label in SIMILARITY_FEATURES
            if abs(own_z[name] - other_z[name]) <= TOP_REASON_Z_THRESHOLD
        ),
        key=lambda item: (item[0], item[1]),
    )
    for _delta, label in close:
        if len(reasons) >= TOP_REASON_LIMIT:
            break
        reasons.append(label)

    if not reasons:
        return "a similar overall history profile"
    return "; ".join(reasons[:TOP_REASON_LIMIT])


# ---------------------------------------------------------------------------
# Convenience: build the whole curated layer in dependency order
# ---------------------------------------------------------------------------

def build_all(
    *,
    changes: Any,
    claims: Any,
    policy_history: Any,
    policy_coverage_history: Any,
    claim_payment: Any = None,
    anchor_date: Any,
    k: int = K_NEIGHBOURS,
) -> dict[str, pd.DataFrame]:
    """All six curated tables, in dependency order.

    Used by the tests and by ``dlt_pipeline.py``'s driver-side build so that the
    ordering constraint — patterns before profile, profile before similarity —
    lives in one place.
    """
    change_event = build_policy_change_event(changes, claims, policy_history, anchor_date)
    claim_event = build_claim_event(
        claims, changes, policy_coverage_history, policy_history, anchor_date
    )
    pattern_match = build_policy_pattern_match(change_event, claim_event)
    profile = build_policy_profile(
        policy_history, policy_coverage_history, change_event, claim_event,
        pattern_match, anchor_date,
    )
    timeline = build_policy_timeline_event(
        changes, claims, claim_payment, policy_history, anchor_date
    )
    similarity = build_policy_similarity(profile, change_event, pattern_match, k=k)
    return {
        "policy_change_event": change_event,
        "claim_event": claim_event,
        "policy_profile": profile,
        "policy_timeline_event": timeline,
        "policy_pattern_match": pattern_match,
        "policy_similarity": similarity,
    }
