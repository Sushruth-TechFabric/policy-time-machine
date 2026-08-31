"""Input-side policy-ID detection (ADR-0007).

The app's only natural-language interpretation: a regex over the raw
question text. Everything else about "what the user meant" is left to
Genie. The pattern is a contract with the generator — `P-` followed by
exactly five digits, lexically reserved so no other identifier
(claim ids, endorsement ids, ...) can embed it.
"""

import re

#: Case-insensitive, word-bounded per ADR-0007.
POLICY_ID_PATTERN = re.compile(r"\bP-\d{5}\b", re.IGNORECASE)


def detect_policy_ids(text: str) -> list[str]:
    """Return distinct policy ids mentioned in `text`, in first-seen order.

    Matches are case-insensitive but normalised to upper-case, since that
    is the canonical form stored in the curated tables.
    """
    seen: dict[str, None] = {}
    for match in POLICY_ID_PATTERN.finditer(text or ""):
        seen.setdefault(match.group(0).upper(), None)
    return list(seen)


def resolve_timeline_policy_id(detected_ids: list[str]) -> str | None:
    """Exactly one distinct id opens a timeline; several or zero suppress."""
    return detected_ids[0] if len(detected_ids) == 1 else None
