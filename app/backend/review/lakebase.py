"""Lakebase access: connections to main, and the Working Branch lifecycle.

Branches fork and never merge (ADR-0017). The harness forks
``run-<run_id>`` from the main branch, adopts the read-write endpoint the
platform provisions with the branch (creating one only where it does not),
connects with a fresh OAuth database credential as password, and deletes
endpoint then branch when the Run ends. A TTL on the branch is the platform backstop for a crashed
process; explicit deletion is the normal path.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import (
    Branch,
    BranchSpec,
    Duration,
    Endpoint,
    EndpointSpec,
    EndpointType,
)

from ..config import (
    LAKEBASE_DATABASE,
    LAKEBASE_HOST,
    LAKEBASE_MAIN_BRANCH,
    LAKEBASE_MAIN_ENDPOINT,
    LAKEBASE_PROJECT_ID,
    LAKEBASE_USER,
    REVIEW_BRANCH_TTL_SECONDS,
)


@dataclass(frozen=True)
class WorkingBranch:
    run_id: str
    branch_name: str
    endpoint_name: str
    host: str


def main_branch_name() -> str:
    return f"projects/{LAKEBASE_PROJECT_ID}/branches/{LAKEBASE_MAIN_BRANCH}"


def main_endpoint_name() -> str:
    return f"{main_branch_name()}/endpoints/{LAKEBASE_MAIN_ENDPOINT}"


def conninfo(client: WorkspaceClient, *, host: str, endpoint_name: str, user: str, database: str) -> dict:
    token = client.postgres.generate_database_credential(endpoint=endpoint_name).token
    return {"host": host, "port": 5432, "dbname": database, "user": user, "password": token, "sslmode": "require"}


def _resolve_user(client: WorkspaceClient) -> str:
    return LAKEBASE_USER or client.current_user.me().user_name


def _resolve_main_host(client: WorkspaceClient) -> str:
    if LAKEBASE_HOST:
        return LAKEBASE_HOST
    return client.postgres.get_endpoint(name=main_endpoint_name()).status.hosts.host


def connect_main(client: WorkspaceClient) -> psycopg.Connection:
    info = conninfo(client, host=_resolve_main_host(client), endpoint_name=main_endpoint_name(),
                    user=_resolve_user(client), database=LAKEBASE_DATABASE)
    return psycopg.connect(**info, autocommit=True)


def connect_branch(client: WorkspaceClient, branch: WorkingBranch) -> psycopg.Connection:
    info = conninfo(client, host=branch.host, endpoint_name=branch.endpoint_name,
                    user=_resolve_user(client), database=LAKEBASE_DATABASE)
    return psycopg.connect(**info, autocommit=True)


class BranchLifecycle:
    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def create(self, run_id: str) -> WorkingBranch:
        branch = self._client.postgres.create_branch(
            parent=f"projects/{LAKEBASE_PROJECT_ID}",
            branch=Branch(spec=BranchSpec(source_branch=main_branch_name(),
                                          ttl=Duration(seconds=REVIEW_BRANCH_TTL_SECONDS))),
            branch_id=f"run-{run_id}",
        ).wait()
        try:
            endpoint = self._read_write_endpoint(branch.name)
        except Exception:
            # A branch left behind holds compute, and only one Working Branch
            # may hold compute at a time; do not wait for the TTL to reap it.
            self._client.postgres.delete_branch(name=branch.name).wait()
            raise
        return WorkingBranch(run_id=run_id, branch_name=branch.name, endpoint_name=endpoint.name,
                             host=endpoint.status.hosts.host)

    def _read_write_endpoint(self, branch_name: str) -> Endpoint:
        # A branch allows one read-write endpoint, and the platform may create
        # it together with the branch; a second create is a BadRequest.
        for endpoint in self._client.postgres.list_endpoints(parent=branch_name):
            if endpoint.status.endpoint_type == EndpointType.ENDPOINT_TYPE_READ_WRITE:
                return endpoint
        return self._client.postgres.create_endpoint(
            parent=branch_name,
            endpoint=Endpoint(spec=EndpointSpec(endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
                                                autoscaling_limit_min_cu=0.5, autoscaling_limit_max_cu=1.0)),
            endpoint_id="primary",
        ).wait()

    def delete(self, branch: WorkingBranch) -> None:
        try:
            self._client.postgres.delete_endpoint(name=branch.endpoint_name).wait()
        except Exception:  # noqa: BLE001 - endpoint may already be gone; the branch delete is what matters
            pass
        self._client.postgres.delete_branch(name=branch.branch_name).wait()
