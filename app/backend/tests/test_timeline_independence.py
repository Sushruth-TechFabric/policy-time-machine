"""ADR-0007: the timeline never blocks on Genie and never depends on it
succeeding. These tests are the demo's insurance policy — they mock
Genie failing/raising and assert the deterministic endpoints are
completely unaffected.
"""

from types import SimpleNamespace

from databricks.sdk.service.sql import StatementState


def _success_response(columns, rows):
    return SimpleNamespace(
        status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
        manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in columns])),
        result=SimpleNamespace(data_array=rows),
        statement_id="stmt-1",
    )


def test_timeline_renders_when_genie_client_would_raise(api, mock_client):
    # Genie is deliberately wired to blow up if touched at all.
    mock_client.genie.start_conversation_and_wait.side_effect = Exception("genie is down")
    mock_client.genie.create_message_and_wait.side_effect = Exception("genie is down")
    mock_client.statement_execution.execute_statement.return_value = _success_response(
        ["event_date", "display_label"], [["2026-01-04", "Address changed"]]
    )

    resp = api.get("/api/policies/P-18492/timeline")

    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["events"] == [{"event_date": "2026-01-04", "display_label": "Address changed"}]
    mock_client.genie.start_conversation_and_wait.assert_not_called()
    mock_client.genie.create_message_and_wait.assert_not_called()


def test_timeline_not_found_when_no_rows(api, mock_client):
    mock_client.statement_execution.execute_statement.return_value = _success_response([], [])

    resp = api.get("/api/policies/P-99999/timeline")

    assert resp.status_code == 200
    assert resp.json() == {"found": False, "events": []}


def test_timeline_survives_warehouse_exception_with_a_clean_error(api, mock_client):
    mock_client.statement_execution.execute_statement.side_effect = Exception("warehouse unreachable")

    resp = api.get("/api/policies/P-18492/timeline")

    # A clean, structured error - not an unhandled 500 crash.
    assert resp.status_code == 502
    assert "warehouse unreachable" in resp.json()["detail"]


def test_similar_and_patterns_also_never_touch_genie(api, mock_client):
    mock_client.statement_execution.execute_statement.return_value = _success_response(
        ["rank", "similar_policy_id"], [[1, "P-20114"]]
    )

    similar_resp = api.get("/api/policies/P-18492/similar")
    patterns_resp = api.get("/api/policies/P-18492/patterns")

    assert similar_resp.status_code == 200
    assert similar_resp.json()["neighbours"] == [{"rank": 1, "similar_policy_id": "P-20114"}]
    assert patterns_resp.status_code == 200
    mock_client.genie.start_conversation_and_wait.assert_not_called()
    mock_client.genie.create_message_and_wait.assert_not_called()
