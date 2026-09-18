"""First-notice claim notes, assembled from fixed phrase pools.

A note has five slots. Four of them have a "tell" variant whose rate differs
between labelled claims and the rest; the rates overlap, so no tell decides
anything alone. Counts are allocated exactly (allocation.py); the stream only
chooses which claims carry a tell and which phrase fills a slot. No phrase
carries a digit, so a note never moves with the anchor date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .allocation import exact_count, pick

#: tell -> (rate among labelled claims, rate among the rest). Spec 01 section 9.
TELL_RATES: dict[str, tuple[float, float]] = {
    "vague_location": (0.55, 0.15),
    "no_police_report": (0.60, 0.25),
    "no_witness_late_night": (0.45, 0.15),
    "line_inconsistent": (0.25, 0.02),
}
#: A police report is expected on these lines only; elsewhere its absence is not a tell.
POLICE_LINES: tuple[str, ...] = ("COLL", "COMP")
#: Off the police lines the no-report phrases still appear, at one class-blind rate.
NEUTRAL_NO_REPORT_RATE = 0.25

OPENING: dict[str, tuple[str, ...]] = {
    "COLL": (
        "Caller reports their vehicle was struck while travelling through a junction.",
        "Caller reports hitting a barrier after losing control on a bend.",
        "Caller reports a collision with another car while changing lanes.",
    ),
    "COMP": (
        "Caller reports the vehicle was taken from where it had been parked.",
        "Caller reports hail damage after a storm.",
        "Caller reports a broken windscreen and items missing from the cabin.",
    ),
    "BI": (
        "Caller reports the other driver was hurt in the incident.",
        "Caller reports a pedestrian was injured.",
        "Caller reports a passenger in the other car complained of neck pain.",
    ),
    "PD": (
        "Caller reports damaging a neighbour's fence while reversing.",
        "Caller reports clipping a parked car.",
        "Caller reports hitting a shop front at low speed.",
    ),
    "UMUIM": (
        "Caller reports being hit by a driver who left without stopping.",
        "Caller reports the other driver had no cover at all.",
        "Caller reports a rear impact from a driver who gave false details.",
    ),
}

DAMAGE: dict[str, tuple[str, ...]] = {
    "COLL": (
        "Front bumper, bonnet and radiator are damaged.",
        "The driver side doors are crushed and will not open.",
        "Rear quarter panel and axle are bent.",
    ),
    "COMP": (
        "Ignition barrel is broken and the stereo is gone.",
        "Roof and bonnet are dented all over.",
        "Glass is shattered; bodywork is otherwise untouched.",
    ),
    "BI": (
        "The injured party was taken to hospital for assessment.",
        "The injured party is reporting ongoing back pain.",
        "An ambulance attended and treated the injured party at the roadside.",
    ),
    "PD": (
        "The fence panels and one post need replacing.",
        "The other vehicle has a scraped door and broken mirror.",
        "The shop window and frame are cracked.",
    ),
    "UMUIM": (
        "Rear bumper and boot lid are pushed in.",
        "Tail lights are smashed and the exhaust is hanging off.",
        "The side of the car is scraped along its full length.",
    ),
}
#: The line whose damage pool a line-inconsistent note borrows from.
INCONSISTENT_WITH: dict[str, str] = {
    "COLL": "COMP", "COMP": "COLL", "BI": "PD", "PD": "BI", "UMUIM": "COMP",
}

WHERE_SPECIFIC = (
    "It happened at the junction by the retail park on the ring road.",
    "It happened outside the caller's home address.",
    "It happened in the multi-storey car park next to the station.",
    "It happened on the northbound carriageway just past the services.",
)
WHERE_VAGUE = (
    "Caller could not say exactly where it happened.",
    "It happened somewhere on the way back from a friend's place.",
    "Location was given only as out of town.",
)
POLICE_REPORTED = (
    "Police attended and gave a reference number.",
    "It was reported to police the same day.",
    "An officer took statements at the scene.",
)
POLICE_NONE = (
    "No police report was made.",
    "Caller did not think it was worth telling the police.",
    "Police were not contacted.",
)
WITNESS_PRESENT = (
    "A passer-by saw it and left contact details.",
    "The other party's passenger saw everything.",
    "A nearby shop has camera footage.",
)
WITNESS_NONE = (
    "It was late at night and nobody else was around.",
    "It happened after midnight with no one else present.",
    "No one saw it; it was the early hours.",
)


def all_phrases() -> list[str]:
    out: list[str] = []
    for pool in (*OPENING.values(), *DAMAGE.values(), WHERE_SPECIFIC, WHERE_VAGUE,
                 POLICE_REPORTED, POLICE_NONE, WITNESS_PRESENT, WITNESS_NONE):
        out.extend(pool)
    return out


def _applies(tell: str, coverage_line: str) -> bool:
    return tell != "no_police_report" or coverage_line in POLICE_LINES


def tells_in(note_text: str, coverage_line: str) -> set[str]:
    """The tells present in a note, recovered from its text alone."""
    found: set[str] = set()
    if any(phrase in note_text for phrase in WHERE_VAGUE):
        found.add("vague_location")
    if coverage_line in POLICE_LINES and any(phrase in note_text for phrase in POLICE_NONE):
        found.add("no_police_report")
    if any(phrase in note_text for phrase in WITNESS_NONE):
        found.add("no_witness_late_night")
    if any(phrase in note_text for phrase in DAMAGE[INCONSISTENT_WITH[coverage_line]]):
        found.add("line_inconsistent")
    return found


def build_notes(claim: pd.DataFrame, labelled: set[str], rng: np.random.Generator) -> pd.DataFrame:
    line = dict(zip(claim["claim_id"], claim["coverage_line"]))
    ordered = sorted(line)

    carries: dict[str, set[str]] = {}
    for tell, (rate_in, rate_out) in TELL_RATES.items():
        chosen: set[str] = set()
        for members, rate in (
            ([c for c in ordered if c in labelled], rate_in),
            ([c for c in ordered if c not in labelled], rate_out),
        ):
            eligible = [c for c in members if _applies(tell, line[c])]
            chosen.update(pick(rng, eligible, exact_count(rate, len(eligible))))
        carries[tell] = chosen

    off_police = [c for c in ordered if line[c] not in POLICE_LINES]
    neutral_none = set(pick(rng, off_police, exact_count(NEUTRAL_NO_REPORT_RATE, len(off_police))))

    def choose(pool: tuple[str, ...]) -> str:
        return pool[int(rng.integers(len(pool)))]

    text: dict[str, str] = {}
    for claim_id in ordered:
        own = line[claim_id]
        no_report = claim_id in carries["no_police_report"] or claim_id in neutral_none
        damage_line = INCONSISTENT_WITH[own] if claim_id in carries["line_inconsistent"] else own
        text[claim_id] = " ".join((
            choose(OPENING[own]),
            choose(WHERE_VAGUE if claim_id in carries["vague_location"] else WHERE_SPECIFIC),
            choose(POLICE_NONE if no_report else POLICE_REPORTED),
            choose(WITNESS_NONE if claim_id in carries["no_witness_late_night"] else WITNESS_PRESENT),
            choose(DAMAGE[damage_line]),
        ))
    return pd.DataFrame({
        "claim_id": claim["claim_id"].to_numpy(),
        "note_text": [text[c] for c in claim["claim_id"]],
    })
