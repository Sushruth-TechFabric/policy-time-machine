"""POST /api/investigations/{id}/messages with Genie mocked through its
four contract states: ok, error, empty, clarification. ADR-0007's rule
that the Genie call must never prevent detected ids from being carried
is asserted directly.
"""

from types import SimpleNamespace

import backend.genie as genie_module


def _attachment(query=None, text=None, attachment_id="att-1"):
    return SimpleNamespace(query=query, text=text, attachment_id=attachment_id)


def _message(status="COMPLETED", attachments=None, error=None, conversation_id="conv-1", msg_id="msg-1"):
    return SimpleNamespace(
        status=status,
        attachments=attachments or [],
        error=error,
        conversation_id=conversation_id,
        id=msg_id,
        space_id="space-1",
    )


def _start_investigation(api) -> str:
    return api.post("/api/investigations").json()["investigation_id"]


def test_create_investigation_returns_uuid(api):
    resp = api.post("/api/investigations")
    assert resp.status_code == 200
    investigation_id = resp.json()["investigation_id"]
    assert isinstance(investigation_id, str) and len(investigation_id) > 0


def test_unknown_investigation_id_returns_404(api):
    resp = api.post("/api/investigations/does-not-exist/messages", json={"question": "hi"})
    assert resp.status_code == 404


def test_message_ok(api, mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    query = SimpleNamespace(query="SELECT * FROM policy_timeline_event", description="desc")
    mock_client.genie.start_conversation_and_wait.return_value = _message(attachments=[_attachment(query=query)])
    mock_client.genie.get_message_attachment_query_result.return_value = SimpleNamespace(
        statement_response=SimpleNamespace(
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name="policy_id")])),
            result=SimpleNamespace(data_array=[["P-18492"]]),
        )
    )

    inv = _start_investigation(api)
    resp = api.post(f"/api/investigations/{inv}/messages", json={"question": "What changed on P-18492?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_policy_ids"] == ["P-18492"]
    assert body["timeline_policy_id"] == "P-18492"
    assert body["genie"] == {
        "status": "ok",
        "columns": [{"name": "policy_id"}],
        "rows": [["P-18492"]],
        "generated_sql": "SELECT * FROM policy_timeline_event",
        "description": "desc",
        "error": None,
    }


def test_message_error_from_genie_exception_still_carries_detected_ids(api, mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    mock_client.genie.start_conversation_and_wait.side_effect = Exception("timed out")

    inv = _start_investigation(api)
    resp = api.post(
        f"/api/investigations/{inv}/messages",
        json={"question": "Compare P-18492 and P-20114"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_policy_ids"] == ["P-18492", "P-20114"]
    assert body["timeline_policy_id"] is None  # two ids -> suppressed (ADR-0007)
    assert body["genie"]["status"] == "error"
    assert body["genie"]["error"]


def test_message_error_when_genie_unconfigured(api, mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", None)

    inv = _start_investigation(api)
    resp = api.post(f"/api/investigations/{inv}/messages", json={"question": "What changed on P-18492?"})

    body = resp.json()
    assert body["detected_policy_ids"] == ["P-18492"]
    assert body["timeline_policy_id"] == "P-18492"
    assert body["genie"]["status"] == "error"
    mock_client.genie.start_conversation_and_wait.assert_not_called()


def test_message_empty_result(api, mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    query = SimpleNamespace(query="SELECT 1 WHERE 1=0", description="desc")
    mock_client.genie.start_conversation_and_wait.return_value = _message(attachments=[_attachment(query=query)])
    mock_client.genie.get_message_attachment_query_result.return_value = SimpleNamespace(
        statement_response=SimpleNamespace(
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[])),
            result=SimpleNamespace(data_array=[]),
        )
    )

    inv = _start_investigation(api)
    resp = api.post(f"/api/investigations/{inv}/messages", json={"question": "Anything on P-99999?"})

    assert resp.json()["genie"]["status"] == "empty"


def test_message_clarification(api, mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    text = SimpleNamespace(content="Which policy did you mean?")
    mock_client.genie.start_conversation_and_wait.return_value = _message(attachments=[_attachment(text=text)])

    inv = _start_investigation(api)
    resp = api.post(f"/api/investigations/{inv}/messages", json={"question": "What changed recently?"})

    body = resp.json()
    assert body["genie"]["status"] == "clarification"
    assert body["genie"]["description"] == "Which policy did you mean?"
    assert body["detected_policy_ids"] == []
    assert body["timeline_policy_id"] is None


def test_second_turn_uses_create_message_with_carried_conversation_id(api, mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    query = SimpleNamespace(query="SELECT 1", description="desc")
    mock_client.genie.start_conversation_and_wait.return_value = _message(
        attachments=[_attachment(query=query)], conversation_id="conv-42"
    )
    mock_client.genie.create_message_and_wait.return_value = _message(
        attachments=[_attachment(query=query)], conversation_id="conv-42"
    )
    mock_client.genie.get_message_attachment_query_result.return_value = SimpleNamespace(
        statement_response=SimpleNamespace(
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name="c")])),
            result=SimpleNamespace(data_array=[["v"]]),
        )
    )

    inv = _start_investigation(api)
    api.post(f"/api/investigations/{inv}/messages", json={"question": "first turn"})
    api.post(f"/api/investigations/{inv}/messages", json={"question": "second turn"})

    mock_client.genie.start_conversation_and_wait.assert_called_once()
    mock_client.genie.create_message_and_wait.assert_called_once()
    args, kwargs = mock_client.genie.create_message_and_wait.call_args
    assert "conv-42" in args
