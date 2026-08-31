"""Shape-and-value helpers shared by the fifteen query-contract checks.

Deliberately column-name-tolerant: Genie's generated SQL legitimately
rephrases column aliases between runs, so contracts assert on values
reachable through a handful of keyword matches on the returned column
names, never on the SQL text itself (ADR-0015).
"""

from __future__ import annotations

from typing import Any

from .genie_client import GenieResult


def find_col(columns: list[str], *keyword_groups) -> int | None:
    """Return the index of the first column whose lowercased name contains
    every keyword in `keyword_groups` (each a substring), else None.
    """
    lowered = [c.lower() for c in columns]
    for idx, name in enumerate(lowered):
        if all(kw in name for kw in keyword_groups):
            return idx
    return None


def find_cols_any(columns: list[str], *alternatives: tuple[str, ...]) -> int | None:
    """Try several keyword-group alternatives in order; return first match."""
    for group in alternatives:
        idx = find_col(columns, *group)
        if idx is not None:
            return idx
    return None


def col_values(result: GenieResult, idx: int | None) -> list[Any]:
    if idx is None:
        return []
    return [row[idx] if idx < len(row) else None for row in result.rows]


def row_blob(row: list[Any]) -> str:
    return " | ".join(str(v) for v in row if v is not None).lower()


def extract_policy_ids(result: GenieResult) -> set[str] | None:
    idx = find_col(result.columns, "policy", "id")
    if idx is None:
        return None
    return {str(v).strip() for v in col_values(result, idx) if v is not None}


def has_terminal_data(result: GenieResult) -> bool:
    return result.status == "ok" and bool(result.rows)


def banned_terms_present(text: str, banned: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in banned if term in lowered]
