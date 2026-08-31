"""Parquet emission and the assertions that run at write time.

Checks here are deliberately *emit-time* rather than post-hoc: a lexical
reservation violation silently breaks timeline routing in the application
(ADR-0007), so it has to fail the build rather than surface as a wrong answer.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .constants import COVERAGE_LINES, DEDUCTIBLE_LINES, FAR_FUTURE
from .ids import assert_lexical_reservation

DATE_COLUMNS = {
    "customer": ("customer_since_date",),
    "policy_history": ("effective_from", "effective_to", "term_start_date", "term_end_date"),
    "policy_coverage_history": ("effective_from", "effective_to"),
    "vehicle": ("added_date", "removed_date"),
    "agent": (),
    "claim": ("loss_date", "report_date"),
    "claim_payment": ("payment_date",),
    "scenario_assignment": (),
    "generation_manifest": ("anchor_date",),
}

POLICY_COLUMNS = {"policy_id", "demo_policy_id"}

TABLE_ORDER = (
    "customer",
    "policy_history",
    "policy_coverage_history",
    "vehicle",
    "agent",
    "claim",
    "claim_payment",
    "scenario_assignment",
    "generation_manifest",
)


def assert_source_invariants(frames: dict[str, pd.DataFrame], anchor_date) -> None:
    """Structural invariants the generator owns, checked before anything is written."""
    anchor = pd.Timestamp(anchor_date)
    problems: list[str] = []

    history = frames["policy_history"]
    for name, table in (("policy_history", history), ("policy_coverage_history", frames["policy_coverage_history"])):
        keys = ["policy_id"] + (["coverage_line"] if "coverage_line" in table.columns else [])
        ordered = table.sort_values(keys + ["version_no"], kind="stable")
        group = ordered.groupby(keys, sort=False)
        # Contiguous and non-overlapping: each version starts where the last ended.
        expected_from = group["effective_to"].shift(1)
        mismatch = ordered["effective_from"].ne(expected_from) & expected_from.notna()
        if mismatch.any():
            problems.append(f"{name}: {int(mismatch.sum())} versions are not contiguous")
        if not ordered.loc[ordered["is_current"], "effective_to"].eq(pd.Timestamp(FAR_FUTURE)).all():
            problems.append(f"{name}: a current version does not carry the open-ended marker")
        if group["is_current"].sum().ne(1).any():
            problems.append(f"{name}: a key does not have exactly one current version")
        if ordered["effective_from"].ge(ordered["effective_to"]).any():
            problems.append(f"{name}: a version has a non-positive lifetime")

    coverage = frames["policy_coverage_history"]
    if not set(coverage["coverage_line"]).issubset(set(COVERAGE_LINES)):
        problems.append("policy_coverage_history: unknown coverage line")
    wrong = coverage.loc[~coverage["coverage_line"].isin(DEDUCTIBLE_LINES), "deductible_amount"]
    if wrong.notna().any():
        problems.append("policy_coverage_history: deductible present on a line that has none")
    missing = coverage.loc[coverage["coverage_line"].isin(DEDUCTIBLE_LINES), "deductible_amount"]
    if missing.isna().any():
        problems.append("policy_coverage_history: deductible missing on COLL or COMP")

    claim = frames["claim"]
    if claim["report_date"].lt(claim["loss_date"]).any():
        problems.append("claim: report_date precedes loss_date")
    if claim["report_date"].eq(claim["loss_date"]).any():
        problems.append("claim: a loss-to-report gap of zero days was emitted")

    # No event timestamp may exceed the anchor; attribute dates legitimately may.
    event_columns = {
        "policy_history": ("effective_from",),
        "policy_coverage_history": ("effective_from",),
        "vehicle": ("added_date", "removed_date"),
        "claim": ("loss_date", "report_date"),
        "claim_payment": ("payment_date",),
        "customer": ("customer_since_date",),
    }
    for table, columns in event_columns.items():
        for column in columns:
            series = frames[table][column].dropna()
            if series.gt(anchor).any():
                problems.append(f"{table}.{column}: event date after the anchor")

    payments = frames["claim_payment"].groupby("claim_id")["amount"].sum()
    settled = claim.loc[claim["claim_status"] == "settled"].set_index("claim_id")["settled_amount"]
    joined = settled.to_frame("settled").join(payments.to_frame("paid"), how="left")
    off = (joined["paid"] - joined["settled"]).abs() > 0.011
    if off.fillna(True).any():
        problems.append("claim_payment: payments do not sum to settled_amount on settled claims")

    if problems:
        raise AssertionError("source invariants violated:\n  " + "\n  ".join(problems))


def write(frames: dict[str, pd.DataFrame], out_dir: str | Path, anchor_date) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assert_lexical_reservation(frames, POLICY_COLUMNS)
    assert_source_invariants(frames, anchor_date)

    written: list[Path] = []
    for table in TABLE_ORDER:
        frame = frames[table]
        arrow = pa.Table.from_pandas(frame, preserve_index=False)
        fields = []
        for field in arrow.schema:
            if field.name in DATE_COLUMNS[table]:
                fields.append(pa.field(field.name, pa.date32()))
            else:
                fields.append(field)
        arrow = arrow.cast(pa.schema(fields))
        path = out / f"{table}.parquet"
        pq.write_table(arrow, path, compression="snappy")
        written.append(path)
    return written
