"""OBO wiring: forwarded token -> viewer-scoped client; no header ->
the cached app-identity client (local dev and the whole test suite)."""

from unittest.mock import MagicMock

from backend import deps


def _request_with_headers(headers: dict[str, str]):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_forwarded_token_builds_viewer_client(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return MagicMock(name="viewer-client", config=MagicMock(host="https://x"))

    monkeypatch.setattr(deps, "WorkspaceClient", fake_client)
    deps._app_client.cache_clear()

    deps.get_client(_request_with_headers({"x-forwarded-access-token": "tok-123"}))

    assert captured["token"] == "tok-123"
    assert captured["auth_type"] == "pat"


def test_no_header_returns_cached_app_client(monkeypatch):
    app_client = MagicMock(name="app-client")
    monkeypatch.setattr(deps, "WorkspaceClient", lambda **kwargs: app_client)
    deps._app_client.cache_clear()

    first = deps.get_client(_request_with_headers({}))
    second = deps.get_client(_request_with_headers({}))

    assert first is app_client and second is app_client
