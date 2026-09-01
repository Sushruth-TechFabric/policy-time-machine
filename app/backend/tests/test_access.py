"""Permission-denied detection: platform error types and error-code
markers only — a generic failure must never masquerade as no_access."""

from databricks.sdk.errors import PermissionDenied

from backend.access import NO_ACCESS_MESSAGE, is_permission_denied


def test_sdk_permission_denied_exception_is_detected():
    assert is_permission_denied(PermissionDenied("nope")) is True


def test_error_code_markers_are_detected_in_text():
    assert is_permission_denied("[INSUFFICIENT_PERMISSIONS] Insufficient privileges: ...") is True
    assert is_permission_denied("PERMISSION_DENIED: User does not have SELECT") is True
    assert is_permission_denied(Exception("status 403: PERMISSION_DENIED on table")) is True


def test_ordinary_failures_are_not_no_access():
    assert is_permission_denied("warehouse unreachable") is False
    assert is_permission_denied(Exception("timed out waiting for the warehouse statement")) is False
    assert is_permission_denied(None) is False


def test_message_is_fixed_and_friendly():
    assert "access" in NO_ACCESS_MESSAGE
    assert "PERMISSION_DENIED" not in NO_ACCESS_MESSAGE
