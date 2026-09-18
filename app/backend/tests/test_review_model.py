from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.review.model import FoundationModelClient, ModelOutputError, parse_json_object


def test_parse_json_object_strips_fences_and_prose():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go: {"shape": "x", "question": "y"} thanks') == {"shape": "x", "question": "y"}


def test_parse_json_object_rejects_non_objects():
    with pytest.raises(ModelOutputError):
        parse_json_object("no json here")
    with pytest.raises(ModelOutputError):
        parse_json_object("[1, 2]")


def test_foundation_model_client_queries_endpoint_with_system_and_user():
    client = MagicMock()
    client.serving_endpoints.query.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
    )
    model = FoundationModelClient(client, "databricks-claude-sonnet-4-5")
    text = model.complete("SYS", "USER", max_tokens=100)
    assert text == '{"ok": true}'
    kwargs = client.serving_endpoints.query.call_args.kwargs
    assert kwargs["name"] == "databricks-claude-sonnet-4-5"
    assert kwargs["max_tokens"] == 100
    assert kwargs["temperature"] == 0.0
    roles = [m.role.value if hasattr(m.role, "value") else m.role for m in kwargs["messages"]]
    assert [r.lower() for r in roles] == ["system", "user"]


def test_foundation_model_client_joins_text_blocks_and_drops_reasoning():
    # Reasoning models (databricks-gpt-oss-120b) return content as a list of
    # blocks rather than a string; only the text blocks are the reply.
    client = MagicMock()
    client.serving_endpoints.query.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=[
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": 'think {"not": "this"}'}]},
            {"type": "text", "text": '{"ok": true}'},
        ]))]
    )
    text = FoundationModelClient(client, "databricks-gpt-oss-120b").complete("SYS", "USER")
    assert text == '{"ok": true}'
    assert parse_json_object(text) == {"ok": True}
