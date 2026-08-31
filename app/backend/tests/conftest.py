"""Shared pytest fixtures.

All Databricks SDK calls are mocked here — no live workspace calls in
tests. `mock_client` stands in for a `WorkspaceClient`; `api` is a
`TestClient` wired to the FastAPI app with `get_client` overridden to
return it.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make `backend` importable regardless of the directory pytest is
# invoked from (mirrors how `uvicorn backend.main:app` is run from `app/`).
APP_DIR = Path(__file__).resolve().parents[2]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from backend.deps import get_client  # noqa: E402
from backend.investigations import store  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_investigation_store():
    store._conversations.clear()
    yield
    store._conversations.clear()


@pytest.fixture
def mock_client():
    return MagicMock(name="WorkspaceClient")


@pytest.fixture
def api(mock_client):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_client] = lambda: mock_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_client, None)
