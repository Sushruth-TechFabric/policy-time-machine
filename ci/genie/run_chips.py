#!/usr/bin/env python3
"""Runs every chip in `app/backend/chips.json` through the live Genie space
(spec 08 §3 / ADR-0011). Every chip is a complete, context-free question,
so each gets its own fresh conversation.

Asserts per chip:
  - the response reaches a terminal state (not error, not a clarification
    request — a chip must be answerable outright)
  - Genie produced generated SQL
  - the SQL executes with a non-empty, correctly shaped result (fetched
    via the message query-result endpoint; falls back to re-running the
    generated SQL on the warehouse directly, mirroring
    `app/backend/genie.py`'s own fallback)

An empty chip result is a build failure (ADR-0011) — this script exits
non-zero if any chip fails, but keeps going and reports every failure
rather than stopping at the first one. chips.json is read-only here: a
chip that turns out to be genuinely unanswerable is a defect to report,
not something this script edits.

Usage: cd <repo root> && ci/genie/.venv/bin/python -m ci.genie.run_chips
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from databricks.sdk import WorkspaceClient  # noqa: E402

from ci.genie import config  # noqa: E402
from ci.genie.genie_client import ask_genie  # noqa: E402

CHIPS_PATH = REPO_ROOT / "app" / "backend" / "chips.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_chip_occurrences() -> list[tuple[str, str]]:
    """Returns (context, question) for every entry in the chip bank,
    in file order — duplicates across contexts are each executed once,
    matching "every chip in the bank" literally.
    """
    bank = json.loads(CHIPS_PATH.read_text(encoding="utf-8"))
    occurrences = []
    for context, questions in bank.items():
        for q in questions:
            occurrences.append((context, q))
    return occurrences


def shape_ok(result) -> tuple[bool, str]:
    if not result.rows:
        return False, "zero rows"
    if not result.columns:
        return False, "no column metadata returned alongside the rows"
    bad_rows = [r for r in result.rows if len(r) != len(result.columns)]
    if bad_rows:
        return False, f"{len(bad_rows)} row(s) have a different arity than the {len(result.columns)} columns"
    return True, f"{len(result.rows)} row(s) x {len(result.columns)} column(s)"


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)

    occurrences = load_chip_occurrences()
    unique_questions = list(dict.fromkeys(q for _, q in occurrences))
    print(
        f"[{_now()}] Loaded {len(occurrences)} chip occurrence(s) "
        f"({len(unique_questions)} unique question(s)) from {CHIPS_PATH}",
        flush=True,
    )

    records = []
    failures = []
    for i, (context, question) in enumerate(occurrences, start=1):
        print(f"[{_now()}] [{i}/{len(occurrences)}] ({context}) {question!r} ...", end=" ", flush=True)
        result = ask_genie(
            client, config.GENIE_SPACE_ID, config.WAREHOUSE_ID, config.CATALOG, config.SCHEMA, question
        )

        passed = True
        reasons = []

        if result.status == "error":
            passed = False
            reasons.append(f"Genie error: {result.error}")
        elif result.status == "clarification":
            passed = False
            reasons.append(f"Genie asked a clarifying question instead of answering: {result.description!r}")
        elif result.status == "empty":
            passed = False
            reasons.append("SQL executed but returned zero rows")

        if not result.generated_sql:
            passed = False
            reasons.append("no generated SQL was produced")

        if passed:
            ok, shape_detail = shape_ok(result)
            if not ok:
                passed = False
                reasons.append(f"badly shaped result: {shape_detail}")

        print("PASS" if passed else "FAIL", flush=True)
        record = {
            "context": context,
            "question": question,
            "passed": passed,
            "reasons": reasons,
            "status": result.status,
            "generated_sql": result.generated_sql,
            "description": result.description,
            "row_count": len(result.rows),
            "columns": result.columns,
        }
        records.append(record)
        if not passed:
            failures.append(record)
            print(f"[{_now()}]   reasons: {reasons}", flush=True)
            if result.generated_sql:
                print(f"[{_now()}]   SQL: {result.generated_sql}", flush=True)

        time.sleep(config.SLEEP_BETWEEN_CALLS_SECONDS)

    passed_count = len(occurrences) - len(failures)
    summary = {
        "timestamp": _now(),
        "total": len(occurrences),
        "unique_questions": len(unique_questions),
        "passed": passed_count,
        "failed": len(failures),
        "records": records,
    }

    ts = summary["timestamp"]
    json_path = RESULTS_DIR / f"chips_{ts}.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str))
    (RESULTS_DIR / "chips_latest.json").write_text(json.dumps(summary, indent=2, default=str))

    lines = [
        "Chip Execution Run — Policy Time Machine",
        f"Timestamp: {ts}",
        f"{passed_count}/{len(occurrences)} chip occurrences passed ({len(unique_questions)} unique questions).",
        "",
    ]
    if failures:
        lines.append("FAILURES:")
        for f in failures:
            lines.append(f"  [{f['context']}] {f['question']}")
            lines.append(f"    reasons: {f['reasons']}")
            if f["generated_sql"]:
                lines.append(f"    SQL: {f['generated_sql']}")
        lines.append("")
    lines.append("OVERALL: " + ("PASS" if not failures else "RED — see failures above"))
    summary_text = "\n".join(lines)
    (RESULTS_DIR / f"chips_summary_{ts}.txt").write_text(summary_text)
    (RESULTS_DIR / "chips_summary_latest.txt").write_text(summary_text)

    print("\n" + summary_text)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
