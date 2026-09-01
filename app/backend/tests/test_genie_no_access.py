"""Every Genie path that can carry a permission error collapses to
status "no_access" with the fixed message — never raw grant text."""

from types import SimpleNamespace

from databricks.sdk.errors import PermissionDenied

import backend.genie as genie_module
from backend.access import NO_ACCESS_MESSAGE
from backend.genie import ask_genie


def test_permission_denied_exception_becomes_no_access(mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    mock_client.genie.start_conversation_and_wait.side_effect = PermissionDenied("nope")
    _, result = ask_genie(mock_client, None, "show changes")
    assert result.status == "no_access"
    assert result.error == NO_ACCESS_MESSAGE


def test_failed_message_with_permission_marker_becomes_no_access(mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    mock_client.genie.start_conversation_and_wait.return_value = SimpleNamespace(
        status="FAILED",
        error=SimpleNamespace(error="PERMISSION_DENIED: cannot read ptm_gold", message=None),
        attachments=[],
        conversation_id="c-1",
    )
    _, result = ask_genie(mock_client, None, "show changes")
    assert result.status == "no_access"
    assert result.error == NO_ACCESS_MESSAGE


def test_ordinary_genie_failure_stays_error(mock_client, monkeypatch):
    monkeypatch.setattr(genie_module, "GENIE_SPACE_ID", "space-1")
    mock_client.genie.start_conversation_and_wait.side_effect = Exception("genie is down")
    _, result = ask_genie(mock_client, None, "show changes")
    assert result.status == "error"
    assert "genie is down" in result.error
