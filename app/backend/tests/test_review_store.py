import os

import pytest

from backend.review.store import DISPOSITION_OUTCOMES, InMemoryReviewStore, ReviewStore

CLAIM = {
    "claim_id": "C-1", "policy_id": "P-10155", "coverage_line": "COLL",
    "loss_date": "2026-08-01", "report_date": "2026-08-05",
    "settled_amount": 24700.0, "severity_band": "severe",
}

_KINDS = ["memory"] + (["pg"] if os.environ.get("REVIEW_TEST_PG_DSN") else [])


@pytest.fixture(params=_KINDS)
def store(request):
    if request.param == "memory":
        yield InMemoryReviewStore()
    else:
        import psycopg
        from backend.review.schema import ensure_schema
        conn = psycopg.connect(os.environ["REVIEW_TEST_PG_DSN"], autocommit=True)
        conn.execute("DROP SCHEMA IF EXISTS review CASCADE")
        ensure_schema(conn, None)
        yield ReviewStore(conn)
        conn.close()


def test_claim_run_is_conditional_and_full_lifecycle_promotes_once(store):
    store.upsert_routed_claim(CLAIM, routed_by="rule", routing_rule="High-severity claim reported in the last 90 days.")
    assert store.claim_run("C-1", "run-1") is True
    assert store.claim_run("C-1", "run-2") is False  # in progress -> second caller loses
    store.start_run("run-1", "C-1")
    store.update_run("run-1", current_step="branch_created", step_count=1, branch_name="projects/p/branches/run-run-1")
    assert store.get_run("run-1")["current_step"] == "branch_created"
    store.complete_run("run-1", "C-1", {"sections": {}}, anchor_date="2026-09-17", trace_id="tr-1")
    detail = store.get_claim("C-1")
    assert detail["run_state"] == "brief_ready"
    assert detail["brief"]["sections"] == {}
    assert detail["disposition"] is None
    assert store.pending_claims(10) == []


def test_failed_run_requeues_and_promotes_nothing(store):
    store.upsert_routed_claim(CLAIM, routed_by="on_demand", routing_rule=None)
    assert store.claim_run("C-1", "run-1")
    store.start_run("run-1", "C-1")
    store.fail_run("run-1", "C-1", "genie timed out")
    detail = store.get_claim("C-1")
    assert detail["run_state"] == "queued" and detail["brief"] is None
    assert store.get_run("run-1")["status"] == "failed"
    assert [c["claim_id"] for c in store.pending_claims(10)] == ["C-1"]


def test_disposition_requires_brief_and_records_who_when(store):
    store.upsert_routed_claim(CLAIM, routed_by="rule", routing_rule="r")
    with pytest.raises(LookupError):
        store.record_disposition("C-1", "closer_look", None, "dana@example.com")
    store.claim_run("C-1", "run-1"); store.start_run("run-1", "C-1")
    store.complete_run("run-1", "C-1", {"sections": {}}, anchor_date="2026-09-17", trace_id=None)
    d = store.record_disposition("C-1", "nothing_noteworthy", "renewal-driven", "dana@example.com")
    assert d["outcome"] in DISPOSITION_OUTCOMES and d["recorded_by"] == "dana@example.com" and d["recorded_at"]
    assert store.list_queue()[0]["disposition"]["outcome"] == "nothing_noteworthy"


def test_investigation_conversation_map(store):
    from backend.review.store import MISSING
    assert store.get_conversation("inv-1") is MISSING
    store.create_investigation("inv-1")
    assert store.get_conversation("inv-1") is None
    store.set_conversation("inv-1", "conv-9")
    assert store.get_conversation("inv-1") == "conv-9"


def test_stale_in_progress_claim_can_be_reclaimed(store):
    from datetime import datetime, timezone, timedelta
    store.upsert_routed_claim(CLAIM, routed_by="rule", routing_rule="High-severity claim reported in the last 90 days.")
    assert store.claim_run("C-1", "run-1") is True
    assert store.claim_run("C-1", "run-2") is False
    if isinstance(store, InMemoryReviewStore):
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        store.claims["C-1"]["updated_at"] = old_time
    else:
        store._exec("UPDATE review.routed_claim SET updated_at = now() - interval '30 minutes' WHERE claim_id = 'C-1'")
    assert store.claim_run("C-1", "run-2") is True
    assert store.get_claim("C-1")["active_run_id"] == "run-2"
