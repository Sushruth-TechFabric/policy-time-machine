"""The model's one real decision, constrained (ADR-0018 §4 shapes).

The harness detects the *situation* from the deterministic sections; the
model must produce a question of the matching *shape*. Validation is
structural (shape tag, comparison phrasing, vocabulary), never string
equality, so the model's wording is free within the shape.
"""

from __future__ import annotations

from enum import Enum

from .vocabulary import violations


class Situation(str, Enum):
    RELEVANT_IN_GAP = "relevant_in_gap"
    RELEVANT_BEFORE_LOSS = "relevant_before_loss"
    PATTERN_ONLY = "pattern_only"
    NOTHING_BEFORE = "nothing_before"


_COMPARISON_WORDS = ("versus", "compared", "against")
_WINDOWS = (30, 60, 90)


def detect_situation(relevant_changes: list[dict], patterns: list[dict]) -> Situation:
    if any(r.get("change_timing") == "after_loss_before_report" for r in relevant_changes):
        return Situation.RELEVANT_IN_GAP
    if relevant_changes:
        return Situation.RELEVANT_BEFORE_LOSS
    if patterns:
        return Situation.PATTERN_ONLY
    return Situation.NOTHING_BEFORE


def window_days(relevant_changes: list[dict]) -> int:
    """Smallest of 30/60/90 that covers the nearest before-loss Relevant Change."""
    days = [
        int(r["days_to_next_claim_loss"])
        for r in relevant_changes
        if r.get("days_to_next_claim_loss") is not None and int(r["days_to_next_claim_loss"]) >= 0
    ]
    if not days:
        return 90
    nearest = min(days)
    for w in _WINDOWS:
        if nearest <= w:
            return w
    return 90


def canonical_question(
    situation: Situation,
    *,
    coverage_line: str,
    line_name: str,
    window: int,
    pattern_name: str | None,
) -> str:
    """The harness's fallback when the model's proposal fails validation twice."""
    if situation is Situation.RELEVANT_IN_GAP:
        return (
            f"How often do coverage or deductible changes on the {line_name} line fall inside the "
            f"loss-to-report gap versus before the loss, for changes with a linked claim? Show both counts."
        )
    if situation is Situation.RELEVANT_BEFORE_LOSS:
        return (
            f"How often does a {line_name} limit increase within {window} days before a claim precede a "
            f"high-severity claim, compared with {line_name} increases not followed by a high-severity claim? "
            f"Show both groups with their counts."
        )
    if situation is Situation.PATTERN_ONLY:
        return (
            f"How common is the pattern '{pattern_name}' among policies with high-severity claims versus "
            f"policies without high-severity claims? Show both rates with sample sizes."
        )
    return (
        "What share of high-severity claims had no material change in the 365 days before the loss, "
        "compared with high-severity claims that did? Show both counts."
    )


def validate_question(situation: Situation, proposal: dict) -> str | None:
    question = proposal.get("question") if isinstance(proposal, dict) else None
    if not isinstance(question, str) or not question.strip():
        return "missing question"
    if proposal.get("shape") != situation.value:
        return f"shape must be {situation.value}"
    if not any(word in question.lower() for word in _COMPARISON_WORDS):
        return "question must name a comparison (versus / compared / against)"
    bad = violations(question)
    if bad:
        return f"vocabulary: {', '.join(bad)}"
    return None
