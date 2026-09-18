"""Runtime vocabulary check for model-generated sentences.

Pipeline expectation E18 guards every user-facing string the pipeline
writes. Sentences the agent writes at runtime never pass through the
pipeline, so the same banned list is applied here. A test asserts this
list equals ``pipeline.transformations.BANNED_VOCABULARY``. ADR-0020 scopes the list by surface; the Brief is investigation-surface.
"""

from __future__ import annotations

import re
from typing import Sequence

ACCUSATORY_TERMS: tuple[str, ...] = (
    "fraud", "fraudulent", "suspicious", "scheme", "deceptive",
    "risk score", "anomaly", "anomalous", "red flag",
)
ALWAYS_BANNED: tuple[str, ...] = (
    "guilty", "predicts", "causes", "leads to", "increases the risk of",
)
BANNED_VOCABULARY: tuple[str, ...] = ACCUSATORY_TERMS + ALWAYS_BANNED
SURFACES: tuple[str, ...] = ("investigation", "detector")

#: Words that turn a fact into a judgement. The Brief restates facts only; the
#: detector surface exists to state a judgement, so they apply to the Brief alone.
JUDGEMENT_WORDS: tuple[str, ...] = ("should", "likely", "intent", "deliberately", "probably")

_POLICY_ID = re.compile(r"\bP-\d{5}\b", re.IGNORECASE)


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE)


_INVESTIGATION = [(term, _pattern(term)) for term in BANNED_VOCABULARY + JUDGEMENT_WORDS]
_DETECTOR = [(term, _pattern(term)) for term in ALWAYS_BANNED]

_PERSON = r"(?:policyholder|customer|insured|claimant|driver)"
_PERSON_AS_SUBJECT = (
    re.compile(rf"\b{_PERSON}\b\s+(?:is|was|has|had)\b[^.]*?"
               r"\b(?:fraud\w*|suspicious|deceptive|dishonest|lying)\b", re.IGNORECASE),
    re.compile(rf"\b{_PERSON}\b\s+(?:committed|staged|lied|faked|invented)\b", re.IGNORECASE),
    re.compile(rf"\b(?:fraudulent|suspicious|deceptive|dishonest)\s+{_PERSON}\b", re.IGNORECASE),
)


def violations(text: str, own_policy_id: str | None = None,
               surface: str = "investigation", person_names: Sequence[str] = ()) -> list[str]:
    if surface not in SURFACES:
        raise ValueError(f"unknown surface {surface!r}; expected one of {SURFACES}")
    value = text or ""
    terms = _INVESTIGATION if surface == "investigation" else _DETECTOR
    found = [term for term, pattern in terms if pattern.search(value)]
    if surface == "detector":
        if any(pattern.search(value) for pattern in _PERSON_AS_SUBJECT):
            found.append("person as subject")
        if any(name and name.lower() in value.lower() for name in person_names):
            found.append("person name")
    own = (own_policy_id or "").upper()
    for match in _POLICY_ID.finditer(value):
        if match.group(0).upper() != own:
            found.append(f"policy id {match.group(0).upper()}")
    return found


def is_clean(text: str, own_policy_id: str | None = None,
             surface: str = "investigation", person_names: Sequence[str] = ()) -> bool:
    return not violations(text, own_policy_id, surface, person_names)
