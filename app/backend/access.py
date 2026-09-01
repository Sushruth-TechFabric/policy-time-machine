"""Shared permission-denied detection (OBO access control).

With on-behalf-of-user auth, a viewer without Unity Catalog grants
surfaces as permission errors from two directions: Genie message
failures and warehouse statement failures. Both funnel through
`is_permission_denied` so they collapse to one `no_access` state
carrying `NO_ACCESS_MESSAGE` — never the raw grant error text.

Detection matches the platform's error types and error codes, not
loose prose: the SDK's `PermissionDenied`, or the documented
`PERMISSION_DENIED` / `INSUFFICIENT_PERMISSIONS` codes embedded in
error text (statement failures arrive as text via `ServiceError`).
"""

from __future__ import annotations

from databricks.sdk.errors import PermissionDenied

NO_ACCESS_MESSAGE = (
    "You don't have access to the policy data behind this workbench. "
    "Ask your workspace admin for access to the gold tables."
)

_ERROR_CODE_MARKERS = ("PERMISSION_DENIED", "INSUFFICIENT_PERMISSIONS")


def is_permission_denied(error: BaseException | str | None) -> bool:
    if error is None:
        return False
    if isinstance(error, PermissionDenied):
        return True
    text = str(error).upper()
    return any(marker in text for marker in _ERROR_CODE_MARKERS)
