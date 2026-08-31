"""Deterministic SQL against the warehouse — zero Genie involvement.

Backs `/api/policies/{id}/timeline`, `/similar` and `/patterns`
(ADR-0007): these read the curated tables directly so they render
whether Genie succeeds, times out, or misbehaves.
"""

from __future__ import annotations

import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState

from .config import CATALOG, SCHEMA, WAREHOUSE_ID

#: How long to keep polling `get_statement` after the initial synchronous
#: wait_timeout window, before giving up. Kept short — these are simple,
#: indexed point lookups, not open-ended Genie queries.
_MAX_POLLS = 30
_POLL_INTERVAL_SECONDS = 1.0


class WarehouseError(RuntimeError):
    """A deterministic query could not be completed.

    Callers turn this into a clean HTTP error rather than a crash — the
    app must keep serving other endpoints (chips, health) even when the
    warehouse or the curated tables are unavailable.
    """


def run_query(
    client: WorkspaceClient,
    statement: str,
    parameters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Execute `statement` and return rows as `{column: value}` dicts."""
    params = [
        StatementParameterListItem(name=name, value=value, type="STRING")
        for name, value in (parameters or {}).items()
    ]
    try:
        response = client.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=statement,
            catalog=CATALOG,
            schema=SCHEMA,
            parameters=params or None,
            wait_timeout="30s",
        )
        response = _await_completion(client, response)
    except WarehouseError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean error upstream
        raise WarehouseError(str(exc)) from exc

    status = getattr(response, "status", None)
    if status is None or status.state != StatementState.SUCCEEDED:
        error = getattr(status, "error", None) if status else None
        message = getattr(error, "message", None) or f"statement did not succeed: {status}"
        raise WarehouseError(message)

    columns: list[str] = []
    manifest = getattr(response, "manifest", None)
    if manifest and manifest.schema and manifest.schema.columns:
        columns = [c.name for c in manifest.schema.columns]

    result = getattr(response, "result", None)
    data_array = (result.data_array if result else None) or []
    return [dict(zip(columns, row)) for row in data_array]


def _await_completion(client: WorkspaceClient, response):
    """Poll a still-running statement until it reaches a terminal state."""
    polls = 0
    status = getattr(response, "status", None)
    while status is not None and status.state in (StatementState.PENDING, StatementState.RUNNING):
        if polls >= _MAX_POLLS:
            raise WarehouseError("timed out waiting for the warehouse statement to complete")
        time.sleep(_POLL_INTERVAL_SECONDS)
        response = client.statement_execution.get_statement(response.statement_id)
        status = getattr(response, "status", None)
        polls += 1
    return response
