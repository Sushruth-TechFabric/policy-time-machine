import re

import numpy as np
import pandas as pd

from generator import notes
from generator.allocation import exact_count

LINES = ("COLL", "COMP", "BI", "PD", "UMUIM")


def book(n=1000):
    ids = [f"CLM-{i:08d}" for i in range(10_000_000, 10_000_000 + n)]
    return pd.DataFrame({"claim_id": ids, "coverage_line": [LINES[i % 5] for i in range(n)]})


def built(seed=3):
    claim = book()
    labelled = set(claim["claim_id"][::10])          # 100 labelled, 900 not
    out = notes.build_notes(claim, labelled, np.random.default_rng(seed))
    return claim, labelled, out


def test_one_note_per_claim_in_claim_order():
    claim, _, out = built()
    assert list(out["claim_id"]) == list(claim["claim_id"])
    assert out["note_text"].str.len().gt(40).all()


def test_same_stream_same_notes():
    assert built(3)[2].equals(built(3)[2])
    assert not built(3)[2].equals(built(4)[2])


def test_tell_counts_are_exact_per_class():
    claim, labelled, out = built()
    line = dict(zip(claim["claim_id"], claim["coverage_line"]))
    found = {c: notes.tells_in(t, line[c]) for c, t in zip(out["claim_id"], out["note_text"])}
    for tell, (rate_in, rate_out) in notes.TELL_RATES.items():
        applies = lambda c: tell != "no_police_report" or line[c] in notes.POLICE_LINES
        inside = [c for c in found if c in labelled and applies(c)]
        outside = [c for c in found if c not in labelled and applies(c)]
        assert sum(tell in found[c] for c in inside) == exact_count(rate_in, len(inside)), tell
        assert sum(tell in found[c] for c in outside) == exact_count(rate_out, len(outside)), tell


def test_off_police_lines_carry_the_no_report_phrases_class_blind():
    """`tells_in` gates the tell on the coverage line, so it can never report
    ``no_police_report`` off the police lines regardless of the note text —
    that alone would make the check unfalsifiable. What actually keeps the
    phrase from leaking the label off those lines is that the no-report
    phrases are allocated to a fixed, class-blind share of off-police claims
    (`NEUTRAL_NO_REPORT_RATE`), independent of `labelled`. Pin both facts."""
    claim, _, out = built()
    line = dict(zip(claim["claim_id"], claim["coverage_line"]))
    text = dict(zip(out["claim_id"], out["note_text"]))
    off_police = [c for c in claim["claim_id"] if line[c] not in notes.POLICE_LINES]
    carries_no_report = [c for c in off_police if any(p in text[c] for p in notes.POLICE_NONE)]
    assert len(carries_no_report) == exact_count(notes.NEUTRAL_NO_REPORT_RATE, len(off_police))
    for c in off_police:
        assert "no_police_report" not in notes.tells_in(text[c], line[c])


def test_no_phrase_is_a_substring_of_another():
    phrases = notes.all_phrases()
    assert len(phrases) == len(set(phrases))
    for a in phrases:
        assert not any(a != b and a in b for b in phrases), a


def test_phrases_carry_no_banned_term_identifier_date_or_name():
    from generator import pools
    banned = re.compile(
        r"\b(fraud\w*|suspicious|scheme|deceptive|guilty|risk score|predicts|causes|"
        r"leads to|anomal\w+|red flag)\b", re.IGNORECASE)
    for phrase in notes.all_phrases():
        assert not banned.search(phrase), phrase
        assert not re.search(r"\bP-\d{5}\b", phrase), phrase
        assert not re.search(r"\d", phrase), f"digits pin a note to a date or amount: {phrase}"
        assert not any(name in phrase for name in pools.FIRST_NAMES + pools.LAST_NAMES), phrase
