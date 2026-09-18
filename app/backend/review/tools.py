"""The harness's tool allowlist (ADR-0018).

Deterministic reads are the app's own SQL against gold, as in queries.py;
the Genie tool is the existing conversation client; staging writes rows to
the Working Branch as jsonb; ScratchSql is the one tool the model drives,
and it only ever runs SELECTs on the branch.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from databricks.sdk import WorkspaceClient

from ..config import CATALOG, SCHEMA
from ..genie import GenieResult, ask_genie
from ..warehouse import run_query

_BRONZE = "ptm_bronze"


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolResult:
    rows: list[dict]
    sql: str
    row_count: int


_CLAIM_SQL = f"SELECT * FROM {CATALOG}.{SCHEMA}.claim_event WHERE claim_id = :claim_id"

_SEQUENCE_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_timeline_event
WHERE policy_id = :policy_id
  AND event_date <= CAST(:loss_date AS DATE)
  AND event_date >= date_sub(CAST(:loss_date AS DATE), 365)
ORDER BY event_date
""".strip()

_RELEVANT_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_change_event
WHERE policy_id = :policy_id AND next_claim_id = :claim_id
  AND change_relates_to_claimed_coverage = true
ORDER BY change_date
""".strip()

_PATTERNS_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_pattern_match
WHERE policy_id = :policy_id AND evidence_claim_id = :claim_id
ORDER BY matched_on_date
""".strip()

_SIMILAR_SQL = f"""
SELECT * FROM {CATALOG}.{SCHEMA}.policy_similarity
WHERE policy_id = :policy_id AND rank <= :k
ORDER BY rank
""".strip()

_ANCHOR_SQL = f"SELECT CAST(anchor_date AS STRING) AS anchor_date FROM {CATALOG}.{_BRONZE}.generation_manifest LIMIT 1"


class WarehouseTools:
    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def _run(self, sql: str, params: dict[str, str]) -> ToolResult:
        rows = run_query(self._client, sql, params)
        return ToolResult(rows=rows, sql=sql, row_count=len(rows))

    def claim(self, claim_id: str) -> dict | None:
        rows = run_query(self._client, _CLAIM_SQL, {"claim_id": claim_id})
        return rows[0] if rows else None

    def sequence(self, policy_id: str, loss_date: str) -> ToolResult:
        return self._run(_SEQUENCE_SQL, {"policy_id": policy_id, "loss_date": str(loss_date)})

    def relevant_changes(self, policy_id: str, claim_id: str) -> ToolResult:
        return self._run(_RELEVANT_SQL, {"policy_id": policy_id, "claim_id": claim_id})

    def pattern_matches(self, policy_id: str, claim_id: str) -> ToolResult:
        return self._run(_PATTERNS_SQL, {"policy_id": policy_id, "claim_id": claim_id})

    def similar(self, policy_id: str, k: int = 5) -> ToolResult:
        return self._run(_SIMILAR_SQL, {"policy_id": policy_id, "k": str(k)})

    def anchor_date(self) -> str:
        rows = run_query(self._client, _ANCHOR_SQL)
        return str(rows[0]["anchor_date"]) if rows else ""


class GenieTool:
    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def ask(self, question: str, conversation_id: str | None = None) -> tuple[str | None, GenieResult]:
        return ask_genie(self._client, conversation_id, question)


def stage(conn, table: str, rows: list[dict]) -> None:
    payload = [(i, json.dumps(row, default=str)) for i, row in enumerate(rows, start=1)]
    with conn.cursor() as cur:
        cur.executemany(f"INSERT INTO review.{table} (n, row) VALUES (%s, %s::jsonb)", payload)


_SELECT_ONLY = re.compile(r"^\s*(with\b[\s\S]*?\)\s*)?select\b", re.IGNORECASE)


class ScratchSql:
    """SELECT-only, row-capped, statement-budgeted SQL on the Working Branch."""

    def __init__(self, conn, max_statements: int = 8, max_rows: int = 50) -> None:
        self._conn = conn
        self.max_statements = max_statements
        self.max_rows = max_rows
        self.statements: list[str] = []

    def run(self, sql: str) -> dict[str, Any]:
        if len(self.statements) >= self.max_statements:
            raise BudgetExceeded(f"scratch SQL budget of {self.max_statements} statements exhausted")
        self.statements.append(sql)
        if ";" in sql.strip().rstrip(";") or not _SELECT_ONLY.match(sql or ""):
            return {"error": "only a single SELECT statement is allowed"}
        try:
            with self._conn.transaction(), self._conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '10s'")
                cur.execute("SET LOCAL transaction_read_only = on")
                cur.execute(sql)
                columns = [d.name for d in (cur.description or [])]
                rows = [list(r) for r in cur.fetchmany(self.max_rows)]
        except Exception as exc:  # noqa: BLE001 - the model sees the error and may try again within budget
            return {"error": str(exc)[:300]}
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
