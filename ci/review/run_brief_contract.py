#!/usr/bin/env python3
"""The Brief contract (design spec §11): build a Brief for the demo
policy's latest claim three times and assert the deterministic sections
against the gold tables, the frequency shape against the detected
situation, every sentence against the vocabulary, and — with one injected
Genie failure — that nothing partial reaches main.

Usage: LAKEBASE_PROJECT_ID=policy-time-machine python -m ci.review.run_brief_contract
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from databricks.sdk import WorkspaceClient  # noqa: E402

from backend.genie import GenieResult  # noqa: E402
from backend.review.harness import run_brief  # noqa: E402
from backend.review.lakebase import connect_main  # noqa: E402
from backend.review.questions import detect_situation  # noqa: E402
from backend.review.runner import build_deps  # noqa: E402
from backend.review.schema import ensure_schema  # noqa: E402
from backend.review.store import ReviewStore  # noqa: E402
from backend.review.vocabulary import violations  # noqa: E402
from ci.genie import config  # noqa: E402
from ci.genie.genie_client import run_warehouse_query  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RUNS = 3
SECTION_ORDER = ["sequence", "relevant_changes", "frequency", "similar"]


def _q(client, sql):
    return run_warehouse_query(client, config.WAREHOUSE_ID, config.CATALOG, config.SCHEMA, sql)


def latest_claim(client, policy_id: str) -> dict:
    rows = _q(client, f"SELECT * FROM claim_event WHERE policy_id = '{policy_id}' ORDER BY report_date DESC LIMIT 1")
    if not rows:
        raise SystemExit(f"demo policy {policy_id} has no claims")
    return rows[0]


def check(brief: dict, client, claim: dict) -> list[str]:
    failures = []
    s = brief["sections"]
    if list(s) != SECTION_ORDER:
        failures.append(f"section order {list(s)}")
    pid, cid = claim["policy_id"], claim["claim_id"]
    expected_seq = _q(client, f"SELECT count(*) AS n FROM policy_timeline_event WHERE policy_id='{pid}' AND event_date <= DATE'{claim['loss_date']}' AND event_date >= date_sub(DATE'{claim['loss_date']}', 365)")[0]["n"]
    if int(expected_seq) != s["sequence"]["row_count"]:
        failures.append(f"sequence rows {s['sequence']['row_count']} != {expected_seq}")
    rel = _q(client, f"SELECT change_event_id, change_timing, days_to_next_claim_loss FROM policy_change_event WHERE policy_id='{pid}' AND next_claim_id='{cid}' AND change_relates_to_claimed_coverage = true")
    if {r["change_event_id"] for r in rel} != {r["change_event_id"] for r in s["relevant_changes"]["rows"]}:
        failures.append("relevant change ids differ from policy_change_event")
    pat = _q(client, f"SELECT pattern_code FROM policy_pattern_match WHERE policy_id='{pid}' AND evidence_claim_id='{cid}'")
    expected_situation = detect_situation(rel, pat).value
    if s["relevant_changes"]["situation"] != expected_situation or s["frequency"]["shape"] != expected_situation:
        failures.append(f"situation/shape mismatch: {s['relevant_changes']['situation']}/{s['frequency']['shape']} vs {expected_situation}")
    if s["frequency"]["genie_status"] != "ok" or s["frequency"]["row_count"] == 0:
        failures.append("frequency section has no Genie rows")
    sim = _q(client, f"SELECT similar_policy_id FROM policy_similarity WHERE policy_id='{pid}' AND rank <= 5 ORDER BY rank")
    if [r["similar_policy_id"] for r in sim] != [r["similar_policy_id"] for r in s["similar"]["rows"]]:
        failures.append("neighbours differ from policy_similarity")
    for name, section in s.items():
        if section.get("sentence") and violations(section["sentence"], pid):
            failures.append(f"{name} sentence violates vocabulary: {section['sentence']!r}")
        if "summary" in section or "recommendation" in section:
            failures.append(f"{name} carries a forbidden field")
    # A Brief whose every sentence was dropped is four tables and no prose:
    # technically valid, useless to a reviewer, and invisible to every other
    # check here.
    if dropped_sentences(brief) == len(SECTION_ORDER):
        failures.append("all four sentences were dropped (tighten prompts.SYSTEM)")
    return failures


def dropped_sentences(brief: dict) -> int:
    return sum(1 for section in brief["sections"].values() if section.get("sentence_dropped"))


class FailingGenie:
    def ask(self, question, conversation_id=None):
        return None, GenieResult(status="error", error="injected failure")


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)
    conn = connect_main(client)
    ensure_schema(conn, os.environ.get("APP_SERVICE_PRINCIPAL_ID"))
    store = ReviewStore(conn)
    manifest = run_warehouse_query(client, config.WAREHOUSE_ID, config.CATALOG, config.BRONZE_SCHEMA,
                                   "SELECT demo_policy_id FROM generation_manifest")[0]
    policy_id = manifest["demo_policy_id"] or config.DEMO_POLICY_ID
    claim = latest_claim(client, policy_id)
    contract_claim_id = claim["claim_id"]
    store.upsert_routed_claim({"claim_id": contract_claim_id, "policy_id": policy_id, "coverage_line": claim["coverage_line"],
                               "loss_date": claim["loss_date"], "report_date": claim["report_date"],
                               "settled_amount": float(claim["settled_amount"]), "severity_band": claim["severity_band"]},
                              routed_by="on_demand", routing_rule=None)
    deps = build_deps(client, store, demo_hold_seconds=0)

    records, passes = [], 0
    for i in range(1, RUNS + 1):
        started = time.monotonic()
        outcome = run_brief(contract_claim_id, deps)
        failures = [outcome.failure] if outcome.status != "completed" else check(outcome.brief, client, claim)
        dropped = dropped_sentences(outcome.brief) if outcome.brief else None
        passed = not failures
        passes += passed
        print(f"run {i}/{RUNS}: {'PASS' if passed else 'FAIL'} ({time.monotonic() - started:.0f}s) "
              f"dropped_sentences={dropped} {failures or ''}", flush=True)
        records.append({"run": i, "passed": passed, "failures": failures, "run_id": outcome.run_id, "trace_id": outcome.trace_id,
                        "dropped_sentences": dropped,
                        "question": (outcome.brief or {}).get("sections", {}).get("frequency", {}).get("question")})
        # Reset so the next run rebuilds rather than being skipped as brief_ready.
        conn.execute("DELETE FROM review.brief WHERE claim_id = %s", (contract_claim_id,))
        conn.execute("UPDATE review.routed_claim SET run_state='queued', active_run_id=NULL WHERE claim_id = %s", (contract_claim_id,))

    # Forced failure: nothing partial on main, claim back to queued.
    failing = build_deps(client, store, demo_hold_seconds=0)
    failing.genie = FailingGenie()
    outcome = run_brief(contract_claim_id, failing)
    partial = store.get_claim(contract_claim_id)
    forced_ok = outcome.status == "failed" and partial["brief"] is None and partial["run_state"] == "queued"
    print(f"forced failure: {'PASS' if forced_ok else 'FAIL'} ({outcome.failure})", flush=True)

    summary = {"timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "policy_id": policy_id,
               "claim_id": contract_claim_id, "passes": passes, "of": RUNS, "forced_failure_ok": forced_ok, "runs": records}
    (RESULTS_DIR / f"brief_contract_{summary['timestamp']}.json").write_text(json.dumps(summary, indent=2, default=str))
    return 0 if passes == RUNS and forced_ok else 1


if __name__ == "__main__":
    sys.exit(main())
