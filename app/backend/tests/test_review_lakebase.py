"""Branch lifecycle against a mocked SDK: create branch -> create endpoint
-> read host; delete endpoint then branch, tolerant of a missing endpoint."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.review import lakebase
from backend.review.lakebase import BranchLifecycle, WorkingBranch


def _client():
    client = MagicMock()
    branch = SimpleNamespace(name="projects/ptm/branches/run-abc")
    client.postgres.create_branch.return_value.wait.return_value = branch
    endpoint = SimpleNamespace(
        name="projects/ptm/branches/run-abc/endpoints/primary",
        status=SimpleNamespace(hosts=SimpleNamespace(host="ep-run-abc.example.com")),
    )
    client.postgres.create_endpoint.return_value.wait.return_value = endpoint
    client.postgres.generate_database_credential.return_value = SimpleNamespace(token="tok")
    return client


def test_create_forks_main_and_returns_host(monkeypatch):
    monkeypatch.setattr(lakebase, "LAKEBASE_PROJECT_ID", "ptm")
    monkeypatch.setattr(lakebase, "LAKEBASE_MAIN_BRANCH", "production")
    client = _client()
    wb = BranchLifecycle(client).create("abc")
    assert wb == WorkingBranch(
        run_id="abc",
        branch_name="projects/ptm/branches/run-abc",
        endpoint_name="projects/ptm/branches/run-abc/endpoints/primary",
        host="ep-run-abc.example.com",
    )
    kwargs = client.postgres.create_branch.call_args.kwargs
    assert kwargs["parent"] == "projects/ptm"
    assert kwargs["branch_id"] == "run-abc"
    assert kwargs["branch"].spec.source_branch == "projects/ptm/branches/production"
    assert kwargs["branch"].spec.ttl.seconds == lakebase.REVIEW_BRANCH_TTL_SECONDS


def test_delete_removes_endpoint_then_branch_and_tolerates_missing_endpoint():
    client = _client()
    client.postgres.delete_endpoint.side_effect = RuntimeError("already gone")
    wb = WorkingBranch("abc", "projects/ptm/branches/run-abc", "projects/ptm/branches/run-abc/endpoints/primary", "h")
    BranchLifecycle(client).delete(wb)
    client.postgres.delete_branch.assert_called_once_with(name="projects/ptm/branches/run-abc")


def test_main_endpoint_name_uses_config(monkeypatch):
    monkeypatch.setattr(lakebase, "LAKEBASE_PROJECT_ID", "ptm")
    assert lakebase.main_endpoint_name() == "projects/ptm/branches/production/endpoints/primary"


def test_conninfo_uses_token_as_password_and_requires_ssl(monkeypatch):
    client = _client()
    info = lakebase.conninfo(client, host="h", endpoint_name="e", user="u@x.com", database="review")
    assert info["password"] == "tok"
    assert info["sslmode"] == "require"
    assert info["host"] == "h" and info["user"] == "u@x.com" and info["dbname"] == "review"
    client.postgres.generate_database_credential.assert_called_once_with(endpoint="e")
