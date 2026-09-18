from unittest.mock import MagicMock

import backend.review.api as api_module
from backend.review.context import get_review_store

CLAIM = {"claim_id": "C-1", "policy_id": "P-10155", "coverage_line": "COLL", "loss_date": "2026-08-01",
         "report_date": "2026-08-05", "settled_amount": 24700.0, "severity_band": "severe"}


def _seed_brief(store):
    store.upsert_routed_claim(CLAIM, "rule", "r")
    store.claim_run("C-1", "run-1"); store.start_run("run-1", "C-1")
    store.complete_run("run-1", "C-1", {"sections": {}}, anchor_date="2026-09-17", trace_id="tr")


def test_queue_and_claim_detail(api):
    store = get_review_store(); _seed_brief(store)
    queue = api.get("/api/review/queue").json()["queue"]
    assert queue[0]["claim_id"] == "C-1" and queue[0]["has_brief"] is True
    detail = api.get("/api/review/claims/C-1").json()
    assert detail["brief"] == {"sections": {}} and detail["run_state"] == "brief_ready"
    assert api.get("/api/review/claims/nope").status_code == 404


def test_prepare_brief_upserts_on_demand_and_starts_a_run(api, mock_client, monkeypatch):
    started = {}
    monkeypatch.setattr(api_module, "lookup_claim", lambda client, claim_id: {**CLAIM, "settled_amount": "24700"})
    monkeypatch.setattr(api_module.registry, "start", lambda claim_id, deps: started.setdefault(claim_id, "run-x"))
    monkeypatch.setattr(api_module, "build_deps", lambda client, store: object())
    monkeypatch.setattr(api_module, "_app_client", lambda: MagicMock())
    resp = api.post("/api/review/claims/C-1/brief")
    assert resp.status_code == 200 and resp.json() == {"run_id": "run-x", "started": True, "reason": None}
    assert get_review_store().get_claim("C-1")["routed_by"] == "on_demand"


def test_prepare_brief_reports_in_progress_without_starting_twice(api, monkeypatch):
    get_review_store().upsert_routed_claim(CLAIM, "rule", "r")
    monkeypatch.setattr(api_module, "lookup_claim", lambda client, claim_id: {**CLAIM, "settled_amount": "24700"})
    monkeypatch.setattr(api_module.registry, "start", lambda claim_id, deps: None)
    monkeypatch.setattr(api_module.registry, "run_id_for", lambda claim_id: "run-live")
    monkeypatch.setattr(api_module, "build_deps", lambda client, store: object())
    monkeypatch.setattr(api_module, "_app_client", lambda: MagicMock())
    assert api.post("/api/review/claims/C-1/brief").json() == {"run_id": "run-live", "started": False, "reason": "in_progress"}


def test_prepare_brief_denies_a_viewer_without_access_even_for_a_routed_claim(api, monkeypatch):
    get_review_store().upsert_routed_claim(CLAIM, "rule", "r")
    from backend.warehouse import WarehousePermissionError
    def denied(client, claim_id): raise WarehousePermissionError("no")
    monkeypatch.setattr(api_module, "lookup_claim", denied)
    def must_not_start(claim_id, deps): raise AssertionError("must not start")
    monkeypatch.setattr(api_module.registry, "start", must_not_start)
    assert api.post("/api/review/claims/C-1/brief").json() == {"no_access": True}


def test_prepare_brief_no_access_and_unknown_claim(api, monkeypatch):
    from backend.warehouse import WarehousePermissionError
    def denied(client, claim_id): raise WarehousePermissionError("no")
    monkeypatch.setattr(api_module, "lookup_claim", denied)
    assert api.post("/api/review/claims/C-9/brief").json() == {"no_access": True}
    monkeypatch.setattr(api_module, "lookup_claim", lambda client, claim_id: None)
    assert api.post("/api/review/claims/C-9/brief").status_code == 404


def test_run_status_endpoint(api):
    store = get_review_store(); _seed_brief(store)
    assert api.get("/api/review/runs/run-1").json()["status"] == "completed"
    assert api.get("/api/review/runs/none").status_code == 404


def test_disposition_records_viewer_identity(api):
    store = get_review_store(); _seed_brief(store)
    resp = api.post("/api/review/claims/C-1/disposition", json={"outcome": "closer_look", "note": "see timeline"},
                    headers={"x-forwarded-email": "dana@example.com"})
    assert resp.status_code == 200 and resp.json()["recorded_by"] == "dana@example.com"
    assert api.post("/api/review/claims/C-1/disposition", json={"outcome": "bogus"}).status_code == 400
    store.upsert_routed_claim({**CLAIM, "claim_id": "C-2"}, "rule", "r")
    assert api.post("/api/review/claims/C-2/disposition", json={"outcome": "closer_look"}).status_code == 409
