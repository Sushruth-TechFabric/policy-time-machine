"""Fixed prompts (ADR-0018). Versioned here, never assembled ad hoc.

The system prompt carries the glossary the model must use and the JSON
contracts for its three kinds of turn. Every turn returns exactly one
JSON object.
"""

from __future__ import annotations

import json

from .vocabulary import BANNED_VOCABULARY, JUDGEMENT_WORDS

PROMPT_VERSION = "2026-09-17.1"

LINE_NAMES = {
    "BI": "bodily injury liability", "PD": "property damage liability", "COLL": "collision",
    "COMP": "comprehensive", "UMUIM": "uninsured/underinsured motorist",
}

SYSTEM = f"""You assist a claims examiner by restating facts from staged data. You never judge.

Definitions (use these words exactly):
- Material Change: a policy change in one of five categories — coverage, deductible, vehicle, address, status. Premium and agent changes are Derived Changes: shown, never counted.
- Relevant Change: a coverage or deductible change on the same coverage line the claim was filed against.
- Change Timing: 'before_loss' or 'after_loss_before_report'. The latter means the change fell inside the loss-to-report gap.
- High-Severity Claim: severity band severe or catastrophic.
- Comparison Group: the population a rate is measured against. A rate is never stated without one.
- Noteworthy Pattern: a named, deterministic rule that matched. Never a score.

Rules:
- Never use any of these words: {", ".join(BANNED_VOCABULARY + JUDGEMENT_WORDS)}.
- Never characterise the policyholder. Never say what anyone intended.
- Every sentence states a fact that is present in the staged rows you are shown or that you computed with SQL over them.
- Reply with exactly one JSON object and nothing else. No prose outside the JSON.
"""

_SHAPE_TEXT = {
    "relevant_in_gap": "How often same-line coverage or deductible changes fall inside the loss-to-report gap versus before the loss, for changes with a linked claim, with both counts.",
    "relevant_before_loss": "How often a same-line limit increase within N days before a claim precedes a high-severity claim, compared with same-line increases not followed by one, with both groups and their sizes. N is the window given below.",
    "pattern_only": "How common the named pattern is among policies with high-severity claims versus policies without, with both rates and sample sizes.",
    "nothing_before": "What share of high-severity claims had no material change in the 365 days before the loss, compared with high-severity claims that did, with both counts.",
}


def question_prompt(situation: str, context: dict, rejection: str | None = None) -> str:
    retry = f"\nYour previous proposal was rejected: {rejection}. Fix that and propose again.\n" if rejection else ""
    return f"""Choose the frequency question for this claim.

Detected situation: {situation}
Required shape: {_SHAPE_TEXT[situation]}
Context: {json.dumps(context, default=str)}
{retry}
Write one natural-language question for a text-to-SQL analyst over these tables: policy_change_event, claim_event, policy_profile, policy_pattern_match. Name the coverage line by its full name. The question must ask for a comparison (use 'versus' or 'compared with') and for both groups' counts or rates.

Reply: {{"shape": "{situation}", "question": "<the question>"}}"""


def follow_up_prompt(question: str, preview: dict) -> str:
    return f"""You asked: {question}
The analyst returned: {json.dumps(preview, default=str)}

You may ask ONE narrowing follow-up in the same conversation if, and only if, the result is missing a comparison group or a sample size. Otherwise decline.

Reply: {{"follow_up": "<question>"}} or {{"follow_up": null}}"""


def sentence_prompt(section: str, preview: dict, scratch_history: list[dict], policy_id: str) -> str:
    history = ""
    if scratch_history:
        history = "\nSCRATCH RESULT(S) so far:\n" + "\n".join(json.dumps(h, default=str) for h in scratch_history)
    tables = "review.stage_timeline, review.stage_relevant_changes, review.stage_patterns, review.stage_frequency, review.stage_similar (each: n int, row jsonb — use row->>'column')"
    return f"""Write one sentence for section "{section}" of the Brief for policy {policy_id}.

Staged rows (preview): {json.dumps(preview, default=str)}
{history}
You may first run ONE SELECT over the staged tables ({tables}) to compute a fact, then write the sentence on your next turn. At most three turns.

Reply with ONE of:
{{"sql": "<single SELECT>"}}
{{"sentence": "<one factual sentence, under 40 words, no other policy ids>"}}"""
