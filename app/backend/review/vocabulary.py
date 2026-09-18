"""Runtime vocabulary check for model-generated sentences.

Pipeline expectation E18 guards every user-facing string the pipeline
writes. Sentences the agent writes at runtime never pass through the
pipeline, so the same banned list is applied here. A test asserts this
list equals ``pipeline.transformations.BANNED_VOCABULARY``.
"""

from __future__ import annotations

import re

BANNED_VOCABULARY: tuple[str, ...] = (
    "fraud", "fraudulent", "suspicious", "scheme", "deceptive", "guilty",
    "risk score", "predicts", "causes", "leads to", "increases the risk of",
    "anomaly", "anomalous", "red flag",
)

#: Words that turn a fact into a judgement. The Brief restates facts only.
JUDGEMENT_WORDS: tuple[str, ...] = ("should", "likely", "intent", "deliberately", "probably")

_POLICY_ID = re.compile(r"\bP-\d{5}\b", re.IGNORECASE)


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE)


_BANNED = [(term, _pattern(term)) for term in BANNED_VOCABULARY + JUDGEMENT_WORDS]


def violations(text: str, own_policy_id: str | None = None) -> list[str]:
    found = [term for term, pattern in _BANNED if pattern.search(text or "")]
    own = (own_policy_id or "").upper()
    for match in _POLICY_ID.finditer(text or ""):
        if match.group(0).upper() != own:
            found.append(f"policy id {match.group(0).upper()}")
    return found


def is_clean(text: str, own_policy_id: str | None = None) -> bool:
    return not violations(text, own_policy_id)
