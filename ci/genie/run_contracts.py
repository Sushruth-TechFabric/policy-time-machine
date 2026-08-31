#!/usr/bin/env python3
"""Runs the fifteen query contracts (spec 05 §4) against the live Genie
space, three times each, per spec 08 §4 / ADR-0015.

Ground truth is computed once from the curated tables + `scenario_assignment`
via warehouse SQL (`ground_truth.py`) and never from Genie's own SQL.

Run policy: exactly three runs per contract, always. Never retry until
green — 0/3 is a deterministic break, 1 or 2 of 3 is instruction
ambiguity, and both are reported, not silently retried away.

Usage: ci/genie/.venv/bin/python -m ci.genie.run_contracts
   or: cd ci/genie && .venv/bin/python run_contracts.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from databricks.sdk import WorkspaceClient  # noqa: E402

from ci.genie import config  # noqa: E402
from ci.genie.contracts import CONTRACTS  # noqa: E402
from ci.genie.genie_client import ask_genie  # noqa: E402
from ci.genie.ground_truth import load as load_ground_truth  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RUNS_PER_CONTRACT = 3


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_one(client, gt, contract):
    """Run a single (possibly multi-turn) contract attempt. Returns
    (outcome, diagnostics dict)."""
    if contract.turns:
        q1, q2 = contract.turns
        r1 = ask_genie(client, config.GENIE_SPACE_ID, config.WAREHOUSE_ID, config.CATALOG, config.SCHEMA, q1)
        time.sleep(config.SLEEP_BETWEEN_CALLS_SECONDS)
        r2 = ask_genie(
            client,
            config.GENIE_SPACE_ID,
            config.WAREHOUSE_ID,
            config.CATALOG,
            config.SCHEMA,
            q2,
            conversation_id=r1.conversation_id,
        )
        outcome = contract.check(r1, r2, gt)
        diagnostics = {
            "turn1_question": q1,
            "turn1_generated_sql": r1.generated_sql,
            "turn1_description": r1.description,
            "turn1_status": r1.status,
            "turn2_question": q2,
            "turn2_generated_sql": r2.generated_sql,
            "turn2_description": r2.description,
            "turn2_status": r2.status,
        }
    else:
        q = contract.question.format(demo=gt.demo_policy_id)
        r = ask_genie(client, config.GENIE_SPACE_ID, config.WAREHOUSE_ID, config.CATALOG, config.SCHEMA, q)
        outcome = contract.check(r, gt)
        diagnostics = {
            "question": q,
            "generated_sql": r.generated_sql,
            "description": r.description,
            "status": r.status,
            "row_count": len(r.rows),
            "columns": r.columns,
        }
    return outcome, diagnostics


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)

    print(f"[{_now()}] Loading ground truth from warehouse SQL...", flush=True)
    gt = load_ground_truth(client)
    print(
        f"[{_now()}] Ground truth loaded. anchor_date={gt.anchor_date} demo_policy_id={gt.demo_policy_id}",
        flush=True,
    )

    all_results = []
    overall_pass = True

    for contract in CONTRACTS:
        print(f"\n[{_now()}] === {contract.id} ({contract.contract_type}) ===", flush=True)
        run_records = []
        pass_count = 0
        for run_idx in range(1, RUNS_PER_CONTRACT + 1):
            print(f"[{_now()}]   run {run_idx}/{RUNS_PER_CONTRACT}...", end=" ", flush=True)
            try:
                outcome, diagnostics = run_one(client, gt, contract)
            except Exception as exc:  # noqa: BLE001
                outcome = None
                diagnostics = {"exception": str(exc)}
            if outcome is None:
                passed = False
                detail = f"Unhandled exception during run: {diagnostics.get('exception')}"
            else:
                passed = outcome.passed
                detail = outcome.detail
            print("PASS" if passed else "FAIL", flush=True)
            if not passed:
                print(f"[{_now()}]     detail: {detail}", flush=True)
                for k, v in diagnostics.items():
                    if v not in (None, ""):
                        print(f"[{_now()}]     {k}: {v}", flush=True)
            if passed:
                pass_count += 1
            run_records.append(
                {"run": run_idx, "passed": passed, "detail": detail, "diagnostics": diagnostics}
            )
            time.sleep(config.SLEEP_BETWEEN_CALLS_SECONDS)

        contract_pass = pass_count == RUNS_PER_CONTRACT
        overall_pass = overall_pass and contract_pass
        severity = (
            "green"
            if pass_count == RUNS_PER_CONTRACT
            else ("deterministic-break" if pass_count == 0 else "instruction-ambiguity")
        )
        print(
            f"[{_now()}] {contract.id}: {pass_count}/{RUNS_PER_CONTRACT} ({severity})",
            flush=True,
        )
        all_results.append(
            {
                "id": contract.id,
                "type": contract.contract_type,
                "question": contract.question,
                "turns": contract.turns,
                "pass_count": pass_count,
                "of": RUNS_PER_CONTRACT,
                "severity": severity,
                "runs": run_records,
            }
        )

    summary = {
        "timestamp": _now(),
        "anchor_date": gt.anchor_date,
        "demo_policy_id": gt.demo_policy_id,
        "overall_pass": overall_pass,
        "contracts": all_results,
    }

    ts = summary["timestamp"]
    json_path = RESULTS_DIR / f"contracts_{ts}.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str))
    (RESULTS_DIR / "contracts_latest.json").write_text(json.dumps(summary, indent=2, default=str))

    lines = [
        "Query Contracts Run — Policy Time Machine",
        f"Timestamp: {ts}",
        f"Anchor date: {gt.anchor_date}  Demo policy: {gt.demo_policy_id}",
        "",
    ]
    for c in all_results:
        lines.append(f"{c['id']:6s} [{c['type']:20s}] {c['pass_count']}/{c['of']}  ({c['severity']})")
        if c["pass_count"] < c["of"]:
            for r in c["runs"]:
                if not r["passed"]:
                    lines.append(f"         run {r['run']}: {r['detail']}")
    lines.append("")
    lines.append(f"OVERALL: {'PASS (3/3 on all fifteen)' if overall_pass else 'RED — see failures above'}")
    summary_text = "\n".join(lines)
    (RESULTS_DIR / f"contracts_summary_{ts}.txt").write_text(summary_text)
    (RESULTS_DIR / "contracts_summary_latest.txt").write_text(summary_text)

    print("\n" + summary_text)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
