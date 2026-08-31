"""Genie conversation client.

One Genie conversation per investigation, multi-turn (ADR-0011): the
first message calls `start_conversation_and_wait`, every later message
in the same investigation calls `create_message_and_wait` against the
carried `conversation_id`.

Every failure mode collapses to a `GenieResult` — this module never
raises. The message endpoint's job (ADR-0007) is to keep carrying
detected policy ids regardless of what Genie does, so a Genie
exception must never become an unhandled error that takes the whole
response down with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from databricks.sdk import WorkspaceClient

from .config import GENIE_SPACE_ID, GENIE_TIMEOUT_SECONDS

#: Terminal Genie message statuses that mean "something went wrong" as
#: opposed to "here is an answer". Compared case-insensitively against
#: `message.status` (a str or an enum with a `.value`, depending on SDK
#: version) so this stays resilient to minor SDK differences.
_FAILURE_STATUSES = {"FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}


@dataclass
class GenieResult:
    status: str  # "ok" | "empty" | "error" | "clarification"
    columns: list[dict[str, str]] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    generated_sql: str | None = None
    description: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "columns": self.columns,
            "rows": self.rows,
            "generated_sql": self.generated_sql,
            "description": self.description,
            "error": self.error,
        }


def ask_genie(
    client: WorkspaceClient,
    conversation_id: str | None,
    question: str,
) -> tuple[str | None, GenieResult]:
    """Send `question` into the conversation, starting one if needed.

    Returns `(conversation_id, result)`. `conversation_id` is created
    lazily on the first call and echoed back so the caller can persist
    it against the investigation.
    """
    if not GENIE_SPACE_ID:
        return conversation_id, GenieResult(
            status="error",
            error="Genie is not configured (GENIE_SPACE_ID is unset).",
        )

    timeout = timedelta(seconds=GENIE_TIMEOUT_SECONDS)
    try:
        if conversation_id is None:
            message = client.genie.start_conversation_and_wait(
                GENIE_SPACE_ID, question, timeout=timeout
            )
        else:
            message = client.genie.create_message_and_wait(
                GENIE_SPACE_ID, conversation_id, question, timeout=timeout
            )
    except Exception as exc:  # noqa: BLE001 - any Genie exception/timeout -> status "error"
        return conversation_id, GenieResult(status="error", error=str(exc))

    new_conversation_id = getattr(message, "conversation_id", None) or conversation_id
    return new_conversation_id, _interpret_message(client, message)


def _status_name(message: Any) -> str:
    status = getattr(message, "status", None)
    return str(getattr(status, "value", status) or "").upper()


def _interpret_message(client: WorkspaceClient, message: Any) -> GenieResult:
    status_name = _status_name(message)

    if status_name in _FAILURE_STATUSES:
        error_obj = getattr(message, "error", None)
        error_text = (
            getattr(error_obj, "error", None)
            or getattr(error_obj, "message", None)
            or f"Genie could not answer the question (status: {status_name or 'unknown'})."
        )
        return GenieResult(status="error", error=str(error_text))

    attachments = getattr(message, "attachments", None) or []
    query_attachment = next((a for a in attachments if getattr(a, "query", None)), None)
    text_attachment = next((a for a in attachments if getattr(a, "text", None)), None)

    if query_attachment is None:
        if text_attachment is not None:
            # No SQL came back — Genie is asking something back rather
            # than answering. Its text becomes the clarification prompt.
            content = getattr(text_attachment.text, "content", None) or ""
            return GenieResult(status="clarification", description=content)
        return GenieResult(status="empty")

    query = query_attachment.query
    generated_sql = getattr(query, "query", None)
    description = getattr(query, "description", None)

    try:
        result = client.genie.get_message_attachment_query_result(
            getattr(message, "space_id", None) or GENIE_SPACE_ID,
            getattr(message, "conversation_id", None),
            getattr(message, "id", None) or getattr(message, "message_id", None),
            getattr(query_attachment, "attachment_id", None),
        )
    except Exception as exc:  # noqa: BLE001 - result fetch failing is still a Genie error
        return GenieResult(
            status="error",
            error=str(exc),
            generated_sql=generated_sql,
            description=description,
        )

    statement_response = getattr(result, "statement_response", None)
    columns: list[dict[str, str]] = []
    rows: list[list[Any]] = []
    if statement_response is not None:
        manifest = getattr(statement_response, "manifest", None)
        schema = getattr(manifest, "schema", None) if manifest else None
        if schema and getattr(schema, "columns", None):
            columns = [{"name": c.name} for c in schema.columns]
        stmt_result = getattr(statement_response, "result", None)
        rows = (getattr(stmt_result, "data_array", None) if stmt_result else None) or []

    if not rows:
        return GenieResult(
            status="empty", columns=columns, generated_sql=generated_sql, description=description
        )

    return GenieResult(
        status="ok",
        columns=columns,
        rows=rows,
        generated_sql=generated_sql,
        description=description,
    )
