"""FastAPI dependency wiring for the Databricks SDK client.

A single indirection point so tests can override `get_client` with a
mock via `app.dependency_overrides` instead of touching a real
workspace. Inside Databricks Apps, `WorkspaceClient()` auto-authenticates
from the runtime; locally it uses the DEFAULT CLI profile.
"""

from functools import lru_cache

from databricks.sdk import WorkspaceClient


@lru_cache(maxsize=1)
def get_client() -> WorkspaceClient:
    return WorkspaceClient()
