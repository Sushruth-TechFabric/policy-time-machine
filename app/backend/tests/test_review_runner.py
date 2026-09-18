import threading

from backend.review import runner
from backend.review.harness import RunOutcome
from backend.review.store import InMemoryReviewStore


def _claim(store, cid):
    store.upsert_routed_claim({"claim_id": cid, "policy_id": "P-1", "coverage_line": "COLL", "loss_date": "2026-08-01",
                               "report_date": "2026-08-05", "settled_amount": 1.0, "severity_band": "severe"}, "rule", "r")


def test_work_queue_runs_pending_claims_sequentially_up_to_cap(monkeypatch):
    store = InMemoryReviewStore()
    for cid in ("C-1", "C-2", "C-3"):
        _claim(store, cid)
    order = []
    def fake_run_brief(claim_id, deps, run_id=None):
        order.append(claim_id)
        return RunOutcome("r", claim_id, "completed", None, {}, None, 0.1)
    monkeypatch.setattr(runner, "run_brief", fake_run_brief)
    deps = runner.RunDeps(store=store, warehouse=None, genie=None, model=None, branches=None, connect_branch=None)
    outcomes = runner.work_queue(deps, cap=2)
    assert [o.claim_id for o in outcomes] == order and len(order) == 2


def test_registry_starts_one_thread_per_claim_and_reports_running(monkeypatch):
    store = InMemoryReviewStore(); _claim(store, "C-1")
    gate = threading.Event()
    def slow_run_brief(claim_id, deps, run_id=None):
        gate.wait(timeout=5)
        return RunOutcome(run_id, claim_id, "completed", None, {}, None, 0.1)
    monkeypatch.setattr(runner, "run_brief", slow_run_brief)
    deps = runner.RunDeps(store=store, warehouse=None, genie=None, model=None, branches=None, connect_branch=None)
    reg = runner.RunRegistry()
    run_id = reg.start("C-1", deps)
    assert run_id and reg.is_running("C-1")
    assert reg.start("C-1", deps) is None
    gate.set()
    reg.join("C-1", timeout=5)
    assert not reg.is_running("C-1")
