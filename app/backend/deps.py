"""FastAPI dependency wiring for the Databricks SDK client.

On-behalf-of-user auth: inside Databricks Apps, the platform forwards
the viewer's downscoped OAuth token as `x-forwarded-access-token`
(declared via the app's `user_api_scopes`). When present, every SDK
call this request makes — Genie, evidence re-runs, deterministic
queries — executes as the viewer, so Unity Catalog grants are the
single enforcement point. Without the header (local dev, tests), the
cached app-identity client is used, and tests override `get_client`
via `app.dependency_overrides` exactly as before.
"""

from functools import lru_cache

from databricks.sdk import WorkspaceClient
from fastapi import Request


@lru_cache(maxsize=1)
def _app_client() -> WorkspaceClient:
    return WorkspaceClient()


def get_client(request: Request) -> WorkspaceClient:
    token = request.headers.get("x-forwarded-access-token")
    if not token:
        return _app_client()
    return WorkspaceClient(host=_app_client().config.host, token=token, auth_type="pat")


def viewer_identity(request: Request) -> str | None:
    """Who the viewer is, from the headers Databricks Apps forwards; None
    locally. Used only for attribution on a Disposition (ADR-0019)."""
    return request.headers.get("x-forwarded-email") or request.headers.get("x-forwarded-preferred-username") or None
