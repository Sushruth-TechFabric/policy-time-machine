def test_health(api):
    resp = api.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chips_endpoint_returns_bank_for_known_context(api):
    resp = api.get("/api/chips", params={"context": "investigation_start"})
    assert resp.status_code == 200
    chips = resp.json()["chips"]
    assert isinstance(chips, list) and chips


def test_chips_endpoint_returns_empty_for_unknown_context(api):
    resp = api.get("/api/chips", params={"context": "not-a-real-context"})
    assert resp.status_code == 200
    assert resp.json() == {"chips": []}


def test_chips_endpoint_requires_context_param(api):
    resp = api.get("/api/chips")
    assert resp.status_code == 422
