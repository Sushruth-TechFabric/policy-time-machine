"""Standalone Genie conversation + warehouse client for the CI test layer.

Deliberately a close mirror of `app/backend/genie.py` and
`app/backend/warehouse.py` (read-only references, not imports — this
directory owns its own copy so `ci/genie/` has no runtime dependency on
the app package). Any behavioural drift between this and the app's own
client is itself worth noticing, so keep the two in step by eye.

Every Genie call in this test layer opens a **fresh conversation**
(chips are context-free by design, ADR-0011) except the one multi-turn
query contract (QC-15), which deliberately reuses a conversation id for
its second turn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState

GENIE_TIMEOUT_SECONDS = 60
WAREHOUSE_POLL_MAX = 60
WAREHOUSE_POLL_INTERVAL = 1.0

_FAILURE_STATUSES = {"FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}


@dataclass
class GenieResult:
    status: str  # "ok" | "empty" | "error" | "clarification"
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    generated_sql: str | None = None
    description: str | None = None
    error: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "columns": self.columns,
            "rows": self.rows,
            "generated_sql": self.generated_sql,
            "description": self.description,
            "error": self.error,
        }

    def dict_rows(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]


def _status_name(message: Any) -> str:
    status = getattr(message, "status", None)
    return str(getattr(status, "value", status) or "").upper()


class WarehouseError(RuntimeError):
    pass


def run_warehouse_query(
    client: WorkspaceClient,
    warehouse_id: str,
    catalog: str,
    schema: str,
    statement: str,
    parameters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Execute `statement` on the warehouse directly and return rows as dicts."""
    params = [
        StatementParameterListItem(name=name, value=value, type="STRING")
        for name, value in (parameters or {}).items()
    ]
    response = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        catalog=catalog,
        schema=schema,
        parameters=params or None,
        wait_timeout="30s",
    )
    polls = 0
    status = getattr(response, "status", None)
    while status is not None and status.state in (StatementState.PENDING, StatementState.RUNNING):
        if polls >= WAREHOUSE_POLL_MAX:
            raise WarehouseError("timed out waiting for the warehouse statement to complete")
        time.sleep(WAREHOUSE_POLL_INTERVAL)
        response = client.statement_execution.get_statement(response.statement_id)
        status = getattr(response, "status", None)
        polls += 1

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


def _interpret_message(
    client: WorkspaceClient,
    space_id: str,
    warehouse_id: str,
    catalog: str,
    schema: str,
    message: Any,
) -> GenieResult:
    status_name = _status_name(message)
    conversation_id = getattr(message, "conversation_id", None)
    message_id = getattr(message, "id", None) or getattr(message, "message_id", None)

    if status_name in _FAILURE_STATUSES:
        error_obj = getattr(message, "error", None)
        error_text = (
            getattr(error_obj, "error", None)
            or getattr(error_obj, "message", None)
            or f"Genie could not answer the question (status: {status_name or 'unknown'})."
        )
        return GenieResult(
            status="error",
            error=str(error_text),
            conversation_id=conversation_id,
            message_id=message_id,
        )

    attachments = getattr(message, "attachments", None) or []
    query_attachment = next((a for a in attachments if getattr(a, "query", None)), None)
    text_attachment = next((a for a in attachments if getattr(a, "text", None)), None)

    if query_attachment is None:
        if text_attachment is not None:
            content = getattr(text_attachment.text, "content", None) or ""
            return GenieResult(
                status="clarification",
                description=content,
                conversation_id=conversation_id,
                message_id=message_id,
            )
        return GenieResult(status="empty", conversation_id=conversation_id, message_id=message_id)

    query = query_attachment.query
    generated_sql = getattr(query, "query", None)
    description = getattr(query, "description", None)

    columns: list[str] = []
    rows: list[list[Any]] = []
    try:
        fetch = getattr(client.genie, "get_message_attachment_query_result", None)
        if fetch is not None:
            result = fetch(
                space_id,
                conversation_id,
                message_id,
                getattr(query_attachment, "attachment_id", None),
            )
        else:
            result = client.genie.get_message_query_result(space_id, conversation_id, message_id)
        statement_response = getattr(result, "statement_response", None)
        if statement_response is not None:
            manifest = getattr(statement_response, "manifest", None)
            sch = getattr(manifest, "schema", None) if manifest else None
            if sch and getattr(sch, "columns", None):
                columns = [c.name for c in sch.columns]
            stmt_result = getattr(statement_response, "result", None)
            rows = (getattr(stmt_result, "data_array", None) if stmt_result else None) or []
    except Exception as exc:  # noqa: BLE001
        return GenieResult(
            status="error",
            error=str(exc),
            generated_sql=generated_sql,
            description=description,
            conversation_id=conversation_id,
            message_id=message_id,
        )

    if not rows and generated_sql:
        # Mirror app/backend/genie.py's fallback: re-run the generated SQL
        # directly against the warehouse when no inline data came back.
        try:
            fetched = run_warehouse_query(client, warehouse_id, catalog, schema, generated_sql)
            if fetched:
                columns = list(fetched[0].keys())
                rows = [list(r.values()) for r in fetched]
        except Exception:  # noqa: BLE001 - genuinely-empty stays "empty"
            pass

    if not rows:
        return GenieResult(
            status="empty",
            columns=columns,
            generated_sql=generated_sql,
            description=description,
            conversation_id=conversation_id,
            message_id=message_id,
        )

    return GenieResult(
        status="ok",
        columns=columns,
        rows=rows,
        generated_sql=generated_sql,
        description=description,
        conversation_id=conversation_id,
        message_id=message_id,
    )


def ask_genie(
    client: WorkspaceClient,
    space_id: str,
    warehouse_id: str,
    catalog: str,
    schema: str,
    question: str,
    conversation_id: str | None = None,
    timeout_seconds: int = GENIE_TIMEOUT_SECONDS,
) -> GenieResult:
    """Ask `question`, starting a new conversation unless `conversation_id` is given."""
    timeout = timedelta(seconds=timeout_seconds)
    try:
        if conversation_id is None:
            message = client.genie.start_conversation_and_wait(space_id, question, timeout=timeout)
        else:
            message = client.genie.create_message_and_wait(
                space_id, conversation_id, question, timeout=timeout
            )
    except Exception as exc:  # noqa: BLE001
        return GenieResult(status="error", error=str(exc), conversation_id=conversation_id)

    return _interpret_message(client, space_id, warehouse_id, catalog, schema, message)
