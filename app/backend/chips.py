"""Loads the authored chip bank (docs/specs/03-genie-knowledge.md -> chips.json).

Every chip is a complete, context-free question (ADR-0011) — the bank is
just static text, keyed by on-screen context; no templating happens here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CHIPS_PATH = Path(__file__).resolve().parent / "chips.json"


@lru_cache(maxsize=1)
def load_chip_bank() -> dict[str, list[str]]:
    with CHIPS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def chips_for_context(context: str) -> list[str]:
    return load_chip_bank().get(context, [])
