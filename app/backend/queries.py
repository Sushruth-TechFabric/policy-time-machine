"""The app's three deterministic, Genie-free reads (ADR-0007, ADR-0010).

`policy_timeline_event`, `policy_similarity` and `policy_pattern_match`
are read directly off the warehouse with a parameterised `policy_id`
filter — no Genie involvement, so these render whether Genie succeeds,
times out, or misbehaves.
"""

from __future__ import annotations

from typing import Any

from databricks.sdk import WorkspaceClient

from .config import CATALOG, SCHEMA
from .warehouse import run_query

_TIMELINE_SQL = f"""
SELECT *
FROM {CATALOG}.{SCHEMA}.policy_timeline_event
WHERE policy_id = :policy_id
ORDER BY event_date
""".strip()

_SIMILAR_SQL = f"""
SELECT *
FROM {CATALOG}.{SCHEMA}.policy_similarity
WHERE policy_id = :policy_id
ORDER BY rank
""".strip()

_PATTERNS_SQL = f"""
SELECT *
FROM {CATALOG}.{SCHEMA}.policy_pattern_match
WHERE policy_id = :policy_id
ORDER BY matched_on_date
""".strip()


def get_timeline(client: WorkspaceClient, policy_id: str) -> list[dict[str, Any]]:
    return run_query(client, _TIMELINE_SQL, {"policy_id": policy_id})


def get_similar(client: WorkspaceClient, policy_id: str) -> list[dict[str, Any]]:
    return run_query(client, _SIMILAR_SQL, {"policy_id": policy_id})


def get_patterns(client: WorkspaceClient, policy_id: str) -> list[dict[str, Any]]:
    return run_query(client, _PATTERNS_SQL, {"policy_id": policy_id})
