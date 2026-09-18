# Fraud Ground Truth and the Detector Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plant a hidden per-claim fraud truth and the evidence that separates it (claim notes, behaviour facts), expose the evidence as `ptm_gold.claim_context`, scope the vocabulary rule by surface, and validate all of it on every regeneration — without changing one existing source row.

**Architecture:** Three new generator modules (`behaviour`, `allocation`, `notes`) plus two that may name the label (`truth`, `validate_truth`) run after all existing generation, each on its own named RNG stream, so existing tables stay byte-identical. The pipeline gains one gold table built by the same record-style transformation pattern as the other six. The truth is written to a separate schema and volume (`ptm_eval`) that the app and Genie are never granted.

**Tech Stack:** Python 3, pandas, numpy, pyarrow, pytest; Lakeflow Declarative Pipelines (`dlt`), Databricks Asset Bundles, Unity Catalog.

**Spec:** `docs/superpowers/specs/2026-09-17-fraud-ground-truth-design.md` — read it before any task.

## Global Constraints

- **Byte identity.** For a given seed and anchor, every table in today's `generator/emit.py:TABLE_ORDER` must hash the same before and after this plan. New randomness comes only from new `Builder.rng("<name>")` streams: `truth` and `claim-notes`.
- **Exact allocation, never per-claim coin flips.** Counts are `floor(rate × n + 0.5)`; the RNG only chooses *which* claims.
- **Declared parameters (copy verbatim):** S fraud rate `0.40`; background fraud rate `0.03`; C fraud rate `0`; odds ratios early tenure `3.0`, recent reinstatement `2.5`, new vehicle `1.5` (background only); early tenure = loss within `90` days of inception; "recent" = `0–30` days before the Loss Date inclusive; tell rates (fraud, benign): vague location `(0.55, 0.15)`, no police report `(0.60, 0.25)` on `COLL`/`COMP` only, no witnesses late night `(0.45, 0.15)`, line-inconsistent damage `(0.25, 0.02)`; reference-scorer AUC band `0.78–0.92`; rules-proxy recall `≤ 0.70`, precision `≤ 0.45`; leakage rank correlation `< 0.10`.
- **Where the label may be named.** The strings `fraud`, `is_fraud`, `claim_fraud_truth`, `ptm_eval` may appear only in `generator/truth.py`, `generator/validate_truth.py`, `generator/tests/`, `workflow/`, `ci/`, `docs/`, and (the word "fraud" alone, inside the vocabulary lists) `pipeline/transformations.py`, `app/backend/review/vocabulary.py`. Every other generator top-level module stays clean: `generator/tests/test_generator.py::test_no_banned_vocabulary_anywhere_in_the_generator` enforces it.
- **No absolute date literal** in any `generator/*.py` top-level module (`test_no_absolute_date_literal_in_the_generator`). Test files may use them.
- **Vocabulary default is unchanged in meaning.** `vocabulary_violations(text)` with no `surface` applies the same fourteen terms as today. One deliberate tightening: multi-word terms now tolerate any whitespace run (`risk  score`), matching what the SQL guard `BANNED_RLIKE` already does.
- **Wording.** Docs, comments and commit messages describe a production-bound project at its start, in the vocabulary of `CONTRIBUTING.md` and `docs/roadmap.md`: release gate, stakeholder, platform engineer, first release.
- **Commits** end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Python environments:** generator and backend tests run with `app/.venv/bin/python` from the repo root; pipeline tests run with `cd pipeline && .venv/bin/python -m pytest`.

## File Structure

| File | Responsibility |
|---|---|
| `generator/behaviour.py` (new) | Behaviour facts of a claim from emitted source tables only. Vocabulary-neutral. |
| `generator/allocation.py` (new) | `exact_count`, `pick`, `stratum_counts`: calibrated-not-sampled allocation. Vocabulary-neutral. |
| `generator/notes.py` (new) | Phrase pools, tell rates, note assembly, `tells_in`. Vocabulary-neutral: speaks of "labelled" claims. |
| `generator/truth.py` (new) | Populations, the label draw, the truth table's name and writer, `extend(...)` — the one call `build.py` makes. |
| `generator/validate_truth.py` (new) | Every check in spec §6 plus the summary lines. |
| `generator/build.py`, `emit.py`, `__main__.py`, `validate.py` | Thin wiring only. |
| `pipeline/transformations.py` | Vocabulary split; `CLAIM_CONTEXT_SCHEMA`, `build_claim_context`, key, `build_all` wiring. |
| `pipeline/expectations.py`, `uc_comments.py`, `dlt_pipeline.py` | E21–E23, comments, the gold table and its QA join. |
| `app/backend/review/vocabulary.py`, `ci/genie/ground_truth.py` | Mirror the vocabulary split; fix drift. |
| `workflow/generate_task.py`, `validate_task.py`, `load_source_tables.py` | `ptm_eval` layout, truth directory, loading `claim_note` and the truth table. |
| `docs/…` | ADR-0020, ADR-0021, charter, `CONTEXT.md`, specs 01, 02, 08. |

---

### Task 0: Clean tree (gate — needs the user)

The working tree carries about 35 uncommitted doc edits from the production-framing rewrite. Several overlap files this plan edits (`docs/specs/09-product-charter.md`, `docs/specs/02-semantic-layer.md`, `docs/specs/08-test-strategy.md`, `docs/adr/0016-…`, `pipeline/tests/test_expectations.py`, `databricks.yml`).

- [ ] **Step 1:** Run `git status --short`. If anything other than `demo/` and `docs/community-article.md` is listed, **stop and ask the user to commit the rewrite** (on `main`, then `git rebase main` here, or directly on this branch). Do not commit, stash or revert those edits yourself.
- [ ] **Step 2:** Confirm baseline is green:

```bash
app/.venv/bin/python -m pytest generator/tests -q
(cd pipeline && .venv/bin/python -m pytest -q)
(cd app && .venv/bin/python -m pytest backend/tests -q)
```

Expected: all pass. If not, stop and report; do not fix unrelated failures inside this plan.

---

### Task 1: Byte-identity baseline, behaviour facts, allocation maths

**Files:**
- Create: `generator/tests/golden_hashes.json`, `generator/tests/test_byte_identity.py`
- Create: `generator/behaviour.py`, `generator/allocation.py`
- Test: `generator/tests/test_behaviour.py`, `generator/tests/test_allocation.py`

**Interfaces:**
- Produces: `behaviour.FLAGS: tuple[str, ...] = ("early_tenure", "recent_reinstatement", "new_vehicle")`; `behaviour.claim_flags(frames: dict[str, pd.DataFrame]) -> pd.DataFrame` with columns `claim_id, policy_age_at_loss_days, early_tenure, recent_reinstatement, new_vehicle`, one row per claim, in `frames["claim"]` row order.
- Produces: `allocation.exact_count(rate: float, n: int) -> int`; `allocation.pick(rng, ids: list[str], count: int) -> list[str]`; `allocation.stratum_counts(sizes: dict[tuple, int], log_odds: dict[tuple, float], total: int) -> dict[tuple, int]`.

- [ ] **Step 1: Record golden hashes BEFORE any code change**

```bash
PYTHONPATH=. app/.venv/bin/python - <<'EOF'
import datetime as dt, hashlib, json
import pandas as pd
from generator import build
from generator.emit import TABLE_ORDER
frames = build(42, dt.date(2026, 1, 1))
out = {t: hashlib.sha256(pd.util.hash_pandas_object(frames[t], index=False).values.tobytes()).hexdigest()
       for t in TABLE_ORDER}
json.dump(out, open("generator/tests/golden_hashes.json", "w"), indent=2, sort_keys=True)
print(len(out), "tables hashed")
EOF
```

Expected: `9 tables hashed`.

- [ ] **Step 2: Write the byte-identity test**

`generator/tests/test_byte_identity.py`:

```python
"""Every table that existed before the detection work hashes exactly as it did.

New tables draw from their own named RNG streams, so nothing here may move.
The golden file was recorded from the commit before the first detection change.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

from generator import build

GOLDEN = json.loads((Path(__file__).parent / "golden_hashes.json").read_text())


def table_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=False).values.tobytes()
    ).hexdigest()


def test_pre_existing_tables_are_byte_identical():
    frames = build(42, dt.date(2026, 1, 1))
    moved = [t for t, digest in GOLDEN.items() if table_hash(frames[t]) != digest]
    assert not moved, f"tables changed by the detection work: {moved}"
```

Run: `app/.venv/bin/python -m pytest generator/tests/test_byte_identity.py -q` — Expected: PASS (nothing has changed yet). This test must stay green after every later task.

- [ ] **Step 3: Write failing tests for allocation**

`generator/tests/test_allocation.py`:

```python
import math

import numpy as np
import pytest

from generator.allocation import exact_count, pick, stratum_counts


def test_exact_count_rounds_half_up():
    assert exact_count(0.40, 150) == 60
    assert exact_count(0.03, 1000) == 30
    assert exact_count(0.5, 5) == 3      # 2.5 rounds up, unlike Python's round()
    assert exact_count(0.0, 135) == 0


def test_pick_is_deterministic_sorted_and_sized():
    ids = [f"CLM-{i:03d}" for i in range(20)]
    a = pick(np.random.default_rng(1), ids, 7)
    b = pick(np.random.default_rng(1), ids, 7)
    assert a == b and len(a) == 7 and a == sorted(a) and set(a) <= set(ids)
    assert pick(np.random.default_rng(1), ids, 0) == []


def test_stratum_counts_sum_exactly_and_respect_the_odds():
    sizes = {(False,): 900, (True,): 100}
    log_odds = {(False,): 0.0, (True,): math.log(3.0)}
    counts = stratum_counts(sizes, log_odds, 30)
    assert sum(counts.values()) == 30
    # P(flagged) / P(unflagged) as odds ~ 3.0 within integer rounding.
    odds = lambda k: counts[k] / (sizes[k] - counts[k])
    assert 2.2 < odds((True,)) / odds((False,)) < 4.0


def test_stratum_counts_are_within_one_of_the_logistic_expectation():
    sizes = {(a, b): n for (a, b), n in zip(
        [(False, False), (True, False), (False, True), (True, True)], [860, 80, 50, 10])}
    log_odds = {k: (math.log(3.0) if k[0] else 0.0) + (math.log(1.5) if k[1] else 0.0) for k in sizes}
    counts = stratum_counts(sizes, log_odds, 30)
    assert sum(counts.values()) == 30
    assert all(0 <= counts[k] <= sizes[k] for k in sizes)


def test_stratum_counts_reject_an_impossible_total():
    with pytest.raises(ValueError):
        stratum_counts({(False,): 5}, {(False,): 0.0}, 6)
```

Run: `app/.venv/bin/python -m pytest generator/tests/test_allocation.py -q` — Expected: FAIL, `ModuleNotFoundError: generator.allocation`.

- [ ] **Step 4: Implement `generator/allocation.py`**

```python
"""Calibrated-not-sampled allocation.

The generator does not flip a coin per row when a declared rate has to hold on
every seed. It fixes the count, then lets a seeded stream choose *which* rows.
"""

from __future__ import annotations

import math

import numpy as np


def exact_count(rate: float, n: int) -> int:
    """``rate * n`` rounded half up (Python's ``round`` rounds half to even)."""
    return int(math.floor(rate * n + 0.5))


def pick(rng: np.random.Generator, ids: list[str], count: int) -> list[str]:
    """``count`` of ``ids``, chosen by the stream, returned in sorted order."""
    if count == 0:
        return []
    order = rng.permutation(len(ids))
    return sorted(ids[int(i)] for i in order[:count])


def _expected(sizes, log_odds, intercept: float) -> dict[tuple, float]:
    return {
        key: n / (1.0 + math.exp(-(intercept + log_odds[key])))
        for key, n in sizes.items()
    }


def stratum_counts(
    sizes: dict[tuple, int], log_odds: dict[tuple, float], total: int
) -> dict[tuple, int]:
    """Split ``total`` across strata under a logistic model, by largest remainder.

    The intercept is solved so the expected total equals ``total``; each stratum
    gets the floor of its expectation, and the remainder goes to the largest
    fractional parts (ties broken by stratum key). Every count is therefore
    within one of its expectation and the sum is exact.
    """
    if total < 0 or total > sum(sizes.values()):
        raise ValueError(f"cannot place {total} among {sum(sizes.values())} rows")
    if total == 0:
        return {key: 0 for key in sizes}
    low, high = -60.0, 60.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if sum(_expected(sizes, log_odds, mid).values()) < total:
            low = mid
        else:
            high = mid
    shares = _expected(sizes, log_odds, (low + high) / 2.0)
    counts = {key: min(int(math.floor(value + 1e-9)), sizes[key]) for key, value in shares.items()}
    shortfall = total - sum(counts.values())
    order = sorted(shares, key=lambda key: (-(shares[key] - counts[key]), key))
    for key in order:
        if shortfall == 0:
            break
        if counts[key] < sizes[key]:
            counts[key] += 1
            shortfall -= 1
    return counts
```

Run the allocation tests — Expected: PASS.

- [ ] **Step 5: Write failing tests for behaviour facts**

`generator/tests/test_behaviour.py`:

```python
import datetime as dt

import pandas as pd

from generator.behaviour import FLAGS, claim_flags

DAY0 = dt.date(2025, 1, 1)


def d(offset: int) -> pd.Timestamp:
    return pd.Timestamp(DAY0 + dt.timedelta(days=offset))


def frames(claims, history, vehicles):
    return {
        "claim": pd.DataFrame(claims, columns=["claim_id", "policy_id", "loss_date"]),
        "policy_history": pd.DataFrame(
            history, columns=["policy_id", "version_no", "effective_from", "policy_status"]),
        "vehicle": pd.DataFrame(vehicles, columns=["policy_id", "added_date"]),
    }


def test_flags_are_the_declared_three():
    assert FLAGS == ("early_tenure", "recent_reinstatement", "new_vehicle")


def test_early_tenure_is_inclusive_at_ninety_days():
    f = frames(
        [("A", "P1", d(90)), ("B", "P1", d(91))],
        [("P1", 1, d(0), "active")],
        [("P1", d(0))],
    )
    out = claim_flags(f).set_index("claim_id")
    assert out.loc["A", "policy_age_at_loss_days"] == 90
    assert bool(out.loc["A", "early_tenure"]) and not bool(out.loc["B", "early_tenure"])


def test_reinstatement_counts_entry_into_the_status_within_thirty_days():
    history = [
        ("P1", 1, d(0), "active"), ("P1", 2, d(200), "lapsed"),
        ("P1", 3, d(220), "reinstated"), ("P1", 4, d(230), "reinstated"),
    ]
    f = frames([("A", "P1", d(250)), ("B", "P1", d(251)), ("C", "P1", d(219))],
               history, [("P1", d(0))])
    out = claim_flags(f).set_index("claim_id")["recent_reinstatement"]
    # Entry into the status is d(220); a later version still 'reinstated' is not a new entry.
    assert bool(out["A"]) and not bool(out["B"]) and not bool(out["C"])


def test_new_vehicle_ignores_the_vehicle_the_policy_started_with():
    f = frames([("A", "P1", d(20)), ("B", "P2", d(130))],
               [("P1", 1, d(0), "active"), ("P2", 1, d(0), "active")],
               [("P1", d(0)), ("P2", d(0)), ("P2", d(100))])
    out = claim_flags(f).set_index("claim_id")["new_vehicle"]
    assert not bool(out["A"]) and bool(out["B"])


def test_rows_follow_the_claim_frame_order():
    f = frames([("B", "P1", d(10)), ("A", "P1", d(20))], [("P1", 1, d(0), "active")], [])
    assert list(claim_flags(f)["claim_id"]) == ["B", "A"]
```

Run — Expected: FAIL, module missing.

- [ ] **Step 6: Implement `generator/behaviour.py`**

```python
"""Behaviour facts of a claim, derived from the emitted source tables alone.

Nothing here reads generator internals: the same facts are derived again by the
pipeline (``transformations.build_claim_context``) from the same tables, and a
test holds the two derivations together.
"""

from __future__ import annotations

import pandas as pd

FLAGS: tuple[str, ...] = ("early_tenure", "recent_reinstatement", "new_vehicle")
EARLY_TENURE_DAYS = 90
RECENT_DAYS = 30


def _within(claim: pd.DataFrame, events: pd.DataFrame, column: str) -> pd.Series:
    """True where the policy has an event 0..RECENT_DAYS days before the loss."""
    if events.empty:
        return pd.Series(False, index=claim.index)
    joined = claim[["claim_id", "policy_id", "loss_date"]].merge(events, on="policy_id")
    days = (joined["loss_date"] - joined[column]).dt.days
    hits = set(joined.loc[(days >= 0) & (days <= RECENT_DAYS), "claim_id"])
    return claim["claim_id"].isin(hits)


def claim_flags(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    claim = frames["claim"][["claim_id", "policy_id", "loss_date"]].copy()
    claim["loss_date"] = pd.to_datetime(claim["loss_date"])

    history = frames["policy_history"].sort_values(["policy_id", "version_no"], kind="stable").copy()
    history["effective_from"] = pd.to_datetime(history["effective_from"])
    inception = history.groupby("policy_id")["effective_from"].min()

    claim["policy_age_at_loss_days"] = (
        claim["loss_date"] - claim["policy_id"].map(inception)
    ).dt.days.astype("int64")
    claim["early_tenure"] = claim["policy_age_at_loss_days"] <= EARLY_TENURE_DAYS

    previous = history.groupby("policy_id")["policy_status"].shift(1)
    entered = history.loc[
        (history["policy_status"] == "reinstated") & (previous != "reinstated"),
        ["policy_id", "effective_from"],
    ]
    claim["recent_reinstatement"] = _within(claim, entered, "effective_from")

    vehicle = frames["vehicle"][["policy_id", "added_date"]].copy()
    vehicle["added_date"] = pd.to_datetime(vehicle["added_date"])
    vehicle = vehicle[vehicle["added_date"] > vehicle["policy_id"].map(inception)]
    claim["new_vehicle"] = _within(claim, vehicle, "added_date")

    return claim[["claim_id", "policy_age_at_loss_days", *FLAGS]].reset_index(drop=True)
```

- [ ] **Step 7: Run and commit**

Run: `app/.venv/bin/python -m pytest generator/tests -q` — Expected: all PASS (including the vocabulary and date-literal source scans over the two new modules).

```bash
git add generator/behaviour.py generator/allocation.py generator/tests/golden_hashes.json \
        generator/tests/test_byte_identity.py generator/tests/test_behaviour.py generator/tests/test_allocation.py
git commit -m "Generator: byte-identity baseline, behaviour facts, exact allocation"
```

---

### Task 2: Claim notes

**Files:**
- Create: `generator/notes.py`
- Test: `generator/tests/test_notes.py`

**Interfaces:**
- Consumes: `allocation.exact_count`, `allocation.pick`.
- Produces: `notes.TELL_RATES: dict[str, tuple[float, float]]` (rate among labelled claims, rate among the rest); `notes.POLICE_LINES = ("COLL", "COMP")`; `notes.build_notes(claim: pd.DataFrame, labelled: set[str], rng) -> pd.DataFrame` with columns `claim_id, note_text` in `claim` row order; `notes.tells_in(note_text: str, coverage_line: str) -> set[str]`; `notes.all_phrases() -> list[str]`.
- This module is scanned by the generator vocabulary test. It must never name the label: it speaks only of "labelled" claims.

- [ ] **Step 1: Write the failing tests**

`generator/tests/test_notes.py`:

```python
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


def test_police_tell_is_never_reported_off_the_police_lines():
    claim, _, out = built()
    line = dict(zip(claim["claim_id"], claim["coverage_line"]))
    for c, t in zip(out["claim_id"], out["note_text"]):
        if line[c] not in notes.POLICE_LINES:
            assert "no_police_report" not in notes.tells_in(t, line[c])


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
```

Run: `app/.venv/bin/python -m pytest generator/tests/test_notes.py -q` — Expected: FAIL, module missing.

- [ ] **Step 2: Implement `generator/notes.py`**

```python
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
```

- [ ] **Step 3: Run and commit**

Run: `app/.venv/bin/python -m pytest generator/tests -q` — Expected: all PASS.

```bash
git add generator/notes.py generator/tests/test_notes.py
git commit -m "Generator: templated claim notes with exactly allocated, overlapping tells"
```

---

### Task 3: The truth draw, wired into build, emit and the CLI

**Files:**
- Create: `generator/truth.py`
- Modify: `generator/build.py` (`Builder.run`, near line 124–139), `generator/emit.py` (`DATE_COLUMNS`, `TABLE_ORDER`), `generator/__main__.py`
- Modify: `generator/tests/test_generator.py` (vocabulary test exemption, CLI test)
- Test: `generator/tests/test_truth.py`

**Interfaces:**
- Consumes: `behaviour.FLAGS`, `behaviour.claim_flags`, `allocation.*`, `notes.build_notes`.
- Produces: `truth.TABLE = "claim_fraud_truth"`; `truth.S_RATE = 0.40`; `truth.BACKGROUND_RATE = 0.03`; `truth.ODDS_RATIOS: dict[str, float]`; `truth.populations(frames, planted: dict[str, str | None]) -> pd.Series`; `truth.draw(frames, planted, rng) -> pd.DataFrame[claim_id, is_fraud, population]`; `truth.extend(frames, planted, truth_rng, notes_rng) -> dict[str, pd.DataFrame]` returning `{"claim_note": ..., truth.TABLE: ...}`; `truth.write(frames, truth_dir) -> Path`; `truth.default_dir(out_dir) -> Path` (`<out>/eval`).
- `build(seed, anchor)` now returns eleven frames: the nine existing, `claim_note`, and `claim_fraud_truth`. `emit.TABLE_ORDER` has ten (it never lists the truth table).

- [ ] **Step 1: Write the failing tests**

`generator/tests/test_truth.py`:

```python
import datetime as dt

import pytest

from generator import build, truth
from generator.allocation import exact_count
from generator.behaviour import FLAGS, claim_flags

SEED = 42


@pytest.fixture(scope="module")
def frames():
    return build(SEED, dt.datetime.now(dt.timezone.utc).date())


@pytest.fixture(scope="module")
def labelled(frames):
    return frames[truth.TABLE]


def test_one_truth_row_and_one_note_per_claim(frames, labelled):
    ids = list(frames["claim"]["claim_id"])
    assert list(labelled["claim_id"]) == ids
    assert list(frames["claim_note"]["claim_id"]) == ids
    assert list(labelled.columns) == ["claim_id", "is_fraud", "population"]
    assert set(labelled["population"]) == {"S", "C", "background"}


def test_rates_are_exact_in_every_population(labelled):
    by = labelled.groupby("population")["is_fraud"].agg(["sum", "size"])
    assert by.loc["C", "sum"] == 0
    assert by.loc["S", "sum"] == exact_count(truth.S_RATE, int(by.loc["S", "size"]))
    assert by.loc["background", "sum"] == exact_count(
        truth.BACKGROUND_RATE, int(by.loc["background", "size"]))


def test_control_policies_never_carry_the_label(frames, labelled):
    assignment = frames["scenario_assignment"]
    control = set(assignment.loc[assignment["scenario_id"].str.startswith("C"), "policy_id"])
    on_control = frames["claim"]["policy_id"].isin(control).to_numpy()
    assert not labelled.loc[on_control, "is_fraud"].any()
    assert set(labelled.loc[on_control, "population"]) == {"C"}


def test_early_tenure_raises_the_background_rate(frames, labelled):
    """The one flag common enough to measure; the rarer two expect one or two
    labelled claims each, so only the stratum check in validate_truth binds them."""
    merged = labelled.merge(claim_flags(frames), on="claim_id")
    background = merged[merged["population"] == "background"]
    on, off = background[background["early_tenure"]], background[~background["early_tenure"]]
    assert on["is_fraud"].mean() > 2 * off["is_fraud"].mean()


def test_the_truth_is_owned_by_the_seed_not_the_anchor(frames):
    earlier = build(SEED, dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=400))
    assert frames[truth.TABLE].equals(earlier[truth.TABLE])
    assert frames["claim_note"].equals(earlier["claim_note"])
    other = build(SEED + 1, dt.datetime.now(dt.timezone.utc).date())
    assert not frames[truth.TABLE]["claim_id"].equals(other[truth.TABLE]["claim_id"])


def test_write_keeps_the_truth_out_of_the_source_directory(frames, tmp_path):
    from generator.emit import write
    out = tmp_path / "raw"
    write(frames, out, dt.datetime.now(dt.timezone.utc).date())
    path = truth.write(frames, truth.default_dir(out))
    assert path == out / "eval" / f"{truth.TABLE}.parquet" and path.exists()
    assert (out / "claim_note.parquet").exists()
    assert not (out / f"{truth.TABLE}.parquet").exists()
```

Run: `app/.venv/bin/python -m pytest generator/tests/test_truth.py -q` — Expected: FAIL, `generator.truth` missing.

- [ ] **Step 2: Implement `generator/truth.py`**

```python
"""The hidden per-claim fraud label (ADR-0020, ADR-0021).

One of the two generator modules permitted to name the label; the generator's
source-vocabulary test exempts this file and validate_truth.py by name. The
label is allocated *conditional on behaviour that already exists*, from its own
RNG stream, after every other table is final - so no existing row moves.

No product surface and no agent ever reads this table. It exists so a detector
can be measured.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .allocation import exact_count, pick, stratum_counts
from .behaviour import FLAGS, claim_flags
from .notes import build_notes

TABLE = "claim_fraud_truth"

#: Spec 01 section 9. S is flat: behaviour does not vary inside the planted scenarios.
S_RATE = 0.40
BACKGROUND_RATE = 0.03
#: Applied to the background population only.
ODDS_RATIOS: dict[str, float] = {
    "early_tenure": 3.0,
    "recent_reinstatement": 2.5,
    "new_vehicle": 1.5,
}


def populations(frames: dict[str, pd.DataFrame], planted: dict[str, str | None]) -> pd.Series:
    """``C`` for any claim on a control policy; ``S`` for a claim a noteworthy
    scenario planted; ``background`` otherwise (including ordinary claims that
    happen to land on a noteworthy policy)."""
    assignment = frames["scenario_assignment"]
    control = set(assignment.loc[assignment["scenario_id"].str.startswith("C"), "policy_id"])
    claim = frames["claim"]
    out = []
    for claim_id, policy_id in zip(claim["claim_id"], claim["policy_id"]):
        scenario = planted.get(claim_id)
        if policy_id in control:
            out.append("C")
        elif scenario is not None and scenario.startswith("S"):
            out.append("S")
        else:
            out.append("background")
    return pd.Series(out, index=claim.index, name="population")


def stratum_log_odds(key: tuple[bool, ...]) -> float:
    return sum(math.log(ODDS_RATIOS[flag]) for flag, on in zip(FLAGS, key) if on)


def draw(frames: dict[str, pd.DataFrame], planted: dict[str, str | None],
         rng: np.random.Generator) -> pd.DataFrame:
    table = pd.DataFrame({
        "claim_id": frames["claim"]["claim_id"].to_numpy(),
        "population": populations(frames, planted).to_numpy(),
    })
    flags = claim_flags(frames).set_index("claim_id")

    chosen: list[str] = []
    planted_ids = sorted(table.loc[table["population"] == "S", "claim_id"])
    chosen += pick(rng, planted_ids, exact_count(S_RATE, len(planted_ids)))

    background = sorted(table.loc[table["population"] == "background", "claim_id"])
    strata: dict[tuple[bool, ...], list[str]] = {}
    for claim_id in background:
        key = tuple(bool(flags.at[claim_id, flag]) for flag in FLAGS)
        strata.setdefault(key, []).append(claim_id)
    counts = stratum_counts(
        {key: len(ids) for key, ids in strata.items()},
        {key: stratum_log_odds(key) for key in strata},
        exact_count(BACKGROUND_RATE, len(background)),
    )
    for key in sorted(strata):
        chosen += pick(rng, strata[key], counts[key])

    table["is_fraud"] = table["claim_id"].isin(set(chosen))
    return table[["claim_id", "is_fraud", "population"]]


def extend(frames: dict[str, pd.DataFrame], planted: dict[str, str | None],
           truth_rng: np.random.Generator, notes_rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """The two detection tables, built from finished frames. build.py's one call."""
    table = draw(frames, planted, truth_rng)
    labelled = set(table.loc[table["is_fraud"], "claim_id"])
    claim_note = build_notes(frames["claim"][["claim_id", "coverage_line"]], labelled, notes_rng)
    return {"claim_note": claim_note, TABLE: table}


def default_dir(out_dir: str | Path) -> Path:
    return Path(out_dir) / "eval"


def write(frames: dict[str, pd.DataFrame], truth_dir: str | Path) -> Path:
    """Written apart from the source tables: on the platform this directory is a
    volume in a schema the application and Genie are never granted."""
    directory = Path(truth_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{TABLE}.parquet"
    pq.write_table(pa.Table.from_pandas(frames[TABLE], preserve_index=False), path, compression="snappy")
    return path


def load(truth_dir: str | Path) -> pd.DataFrame:
    return pd.read_parquet(Path(truth_dir) / f"{TABLE}.parquet")
```

- [ ] **Step 3: Wire `build.py`**

In `generator/build.py`, add to the imports beside the other `from .` imports:

```python
from . import truth
```

Replace the end of `Builder.run` — currently:

```python
        self._build_claims()
        return self._frames()
```

with:

```python
        self._build_claims()
        frames = self._frames()
        # Detection tables come last and from their own streams, so every table
        # above is final and unchanged by them (ADR-0021).
        planted = {record["claim_id"]: record["scenario"] for record in self._claim_records}
        frames.update(truth.extend(frames, planted, self.rng("truth"), self.rng("claim-notes")))
        return frames
```

- [ ] **Step 4: Wire `emit.py`**

In `DATE_COLUMNS` add `"claim_note": (),` after the `"generation_manifest"` entry. In `TABLE_ORDER` append `"claim_note",` after `"generation_manifest",`. Do **not** add the truth table to either: `write()` must never put it in the source directory, and `emit.py` stays free of the label's name.

- [ ] **Step 5: Wire the CLI**

In `generator/__main__.py`: add `from . import truth`; in `parse_args` add

```python
    parser.add_argument(
        "--truth-out", default=None,
        help="directory for the evaluation-only table; defaults to <out>/eval",
    )
```

and in `main`, after `paths = write(frames, args.out, anchor)`:

```python
    paths.append(truth.write(frames, args.truth_out or truth.default_dir(args.out)))
```

- [ ] **Step 6: Scope the generator's source-vocabulary test**

In `generator/tests/test_generator.py::test_no_banned_vocabulary_anywhere_in_the_generator`, add above the loop:

```python
    # ADR-0020: the label is named in exactly two modules. Everything else in the
    # generator - including the note phrase pools - stays under this rule.
    detector_modules = {"truth.py", "validate_truth.py"}
```

and change the loop header to:

```python
    for path in sorted(SOURCE_DIR.glob("*.py")):
        if path.name in detector_modules:
            continue
```

In `test_cli_writes_every_table_and_validation_passes`, after the `TABLE_ORDER` loop add:

```python
    assert (out / "eval" / "claim_fraud_truth.parquet").exists()
```

- [ ] **Step 7: Run and commit**

Run: `app/.venv/bin/python -m pytest generator/tests -q` — Expected: all PASS, including `test_byte_identity.py`, the three determinism tests (they now also cover `claim_note`), and `test_no_banned_vocabulary_in_emitted_strings`.

```bash
git add generator/truth.py generator/build.py generator/emit.py generator/__main__.py \
        generator/tests/test_truth.py generator/tests/test_generator.py
git commit -m "Generator: hidden claim label allocated on existing behaviour; notes and label emitted"
```

---

### Task 4: Generator validation of the planted truth

**Files:**
- Create: `generator/validate_truth.py`
- Modify: `generator/validate.py` (`run`, `main`)
- Test: `generator/tests/test_validate_truth.py`

**Interfaces:**
- Consumes: `truth.load`, `truth.default_dir`, `truth.S_RATE`, `truth.BACKGROUND_RATE`, `truth.ODDS_RATIOS`, `truth.stratum_log_odds`, `behaviour.claim_flags`, `behaviour.FLAGS`, `notes.TELL_RATES`, `notes.tells_in`, `notes.all_phrases`, `notes.POLICE_LINES`, `allocation.exact_count`.
- Produces: `validate_truth.AUC_BAND = (0.78, 0.92)`; `validate_truth.auc(scores, labels) -> float`; `validate_truth.reference_scores(view: pd.DataFrame) -> np.ndarray` (`view` carries `coverage_line`, `note_text` and the behaviour flags, one row per claim); `validate_truth.add_checks(report, measurements, frames, truth_dir) -> None` (adds checks named with the prefix `detection:`; sets `measurements["detection"]`); `validate_truth.MIN_EXPECTED_FOR_DIRECTION = 3.0` — a flag's marginal direction is asserted only when it expects at least three labelled claims (on the measured book that is early tenure alone; recent reinstatement and new vehicle expect one or two each and are bound by the stratum check); `validate_truth.summary_lines(measurements) -> list[str]`.
- `validate.run(out_dir, truth_dir=None)`; `validate.main` accepts `--truth-out`.

- [ ] **Step 1: Write the failing tests**

`generator/tests/test_validate_truth.py`:

```python
import datetime as dt

import numpy as np
import pytest

from generator import truth, validate as validation, validate_truth
from generator.__main__ import main as generator_main


def test_auc_handles_ties_and_perfect_separation():
    assert validate_truth.auc(np.array([3.0, 2.0, 1.0, 0.0]), np.array([1, 1, 0, 0])) == 1.0
    assert validate_truth.auc(np.array([1.0, 1.0, 1.0, 1.0]), np.array([1, 0, 1, 0])) == 0.5


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("raw")
    anchor = dt.datetime.now(dt.timezone.utc).date().isoformat()
    assert generator_main(["--seed", "42", "--anchor-date", anchor, "--out", str(out)]) == 0
    return out


def test_every_detection_check_passes_on_a_fresh_build(generated):
    report, measurements = validation.run(generated)
    detection = [c for c in report.checks if c.name.startswith("detection:")]
    assert len(detection) >= 7
    failed = [f"{c.name}: {c.detail}" for c in detection if not c.passed]
    assert not failed, "\n".join(failed)
    low, high = validate_truth.AUC_BAND
    assert low <= measurements["detection"]["reference_auc"] <= high
    assert validate_truth.summary_lines(measurements)


def test_a_relabelled_truth_fails_validation(generated, tmp_path):
    table = truth.load(truth.default_dir(generated)).copy()
    table["is_fraud"] = table["population"].eq("C")     # label exactly the controls
    broken = tmp_path / "eval"
    broken.mkdir()
    table.to_parquet(broken / f"{truth.TABLE}.parquet")
    report, _ = validation.run(generated, truth_dir=broken)
    failed = {c.name for c in report.checks if not c.passed}
    assert "detection: declared rates are exact" in failed


def test_other_seeds_also_pass(tmp_path):
    for seed in (7, 1234):
        out = tmp_path / str(seed)
        anchor = dt.datetime.now(dt.timezone.utc).date().isoformat()
        generator_main(["--seed", str(seed), "--anchor-date", anchor, "--out", str(out)])
        report, _ = validation.run(out)
        failed = [c.name for c in report.checks if c.name.startswith("detection:") and not c.passed]
        assert not failed, f"seed {seed}: {failed}"
```

Run — Expected: FAIL, `generator.validate_truth` missing.

- [ ] **Step 2: Implement `generator/validate_truth.py`**

```python
"""Validation of the planted fraud truth (spec 01 section 9, ADR-0021).

The second of the two generator modules permitted to name the label. Every check
works from the emitted tables and the note text - what a detector can see - plus
the truth table. Rates, strata and tells are allocated by exact count, so those
checks are equalities; only separability and leakage are ranges.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import truth
from .allocation import exact_count
from .behaviour import FLAGS, claim_flags
from .notes import POLICE_LINES, TELL_RATES, all_phrases, tells_in

AUC_BAND = (0.78, 0.92)
PROXY_RECALL_CEILING = 0.70
PROXY_PRECISION_CEILING = 0.45
LEAKAGE_RANK_CORRELATION = 0.10
MIN_EXPECTED_FOR_DIRECTION = 3.0

_BANNED = re.compile(
    r"\b(fraud\w*|suspicious|scheme|deceptive|guilty|risk\s+score|predicts|causes|"
    r"leads\s+to|increases\s+the\s+risk\s+of|anomal\w+|red\s+flag)\b", re.IGNORECASE)
_POLICY_ID = re.compile(r"\bP-\d{5}\b", re.IGNORECASE)


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney AUC with average ranks for ties."""
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    positive = labels.astype(bool)
    n_pos, n_neg = int(positive.sum()), int((~positive).sum())
    return float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _tell_applies(tell: str, coverage_line: str) -> bool:
    return tell != "no_police_report" or coverage_line in POLICE_LINES


def reference_scores(view: pd.DataFrame) -> np.ndarray:
    """Sum of the declared log-odds of the tells present and the flags set.

    ``view`` carries coverage_line, note_text and the behaviour flags. The scorer
    knows the declared parameters and nothing else - not the population, not the
    label. It is the baseline sub-project B's bench must beat.
    """
    scores = np.zeros(len(view))
    for index, (line, text) in enumerate(zip(view["coverage_line"], view["note_text"])):
        present = tells_in(text, line)
        for tell, (rate_in, rate_out) in TELL_RATES.items():
            if not _tell_applies(tell, line):
                continue
            scores[index] += (
                math.log(rate_in / rate_out) if tell in present
                else math.log((1 - rate_in) / (1 - rate_out))
            )
    for flag in FLAGS:
        scores += view[flag].to_numpy(dtype=float) * math.log(truth.ODDS_RATIOS[flag])
    return scores


def _logistic_expectations(sizes: dict[tuple, int], total: int) -> dict[tuple, float]:
    """The validator's own solve, independent of allocation.stratum_counts."""
    low, high = -60.0, 60.0
    expected = lambda a: {k: n / (1 + math.exp(-(a + truth.stratum_log_odds(k)))) for k, n in sizes.items()}
    for _ in range(200):
        mid = (low + high) / 2
        low, high = (mid, high) if sum(expected(mid).values()) < total else (low, mid)
    return expected((low + high) / 2)


def add_checks(report, measurements: dict, frames: dict[str, pd.DataFrame], truth_dir: Path) -> None:
    table = truth.load(truth_dir)
    claim = frames["claim"]
    view = (
        claim[["claim_id", "policy_id", "coverage_line"]]
        .merge(frames["claim_note"], on="claim_id", how="left")
        .merge(table, on="claim_id", how="left")
        .merge(claim_flags(frames), on="claim_id", how="left")
    )
    detection: dict = {}

    complete = (
        len(table) == len(claim) and table["claim_id"].is_unique
        and view["is_fraud"].notna().all() and view["note_text"].notna().all()
    )
    report.add("detection: one label and one note per claim", complete,
               f"{len(table):,} labels, {len(frames['claim_note']):,} notes, {len(claim):,} claims")
    if not complete:
        measurements["detection"] = detection
        return
    view["is_fraud"] = view["is_fraud"].astype(bool)

    # --- declared rates -------------------------------------------------------
    by = view.groupby("population")["is_fraud"].agg(["sum", "size"])
    want = {
        "S": exact_count(truth.S_RATE, int(by["size"].get("S", 0))),
        "background": exact_count(truth.BACKGROUND_RATE, int(by["size"].get("background", 0))),
        "C": 0,
    }
    got = {name: int(by["sum"].get(name, 0)) for name in want}
    detection["labelled_by_population"] = got
    detection["claims_by_population"] = {name: int(by["size"].get(name, 0)) for name in want}
    report.add("detection: declared rates are exact", got == want, f"measured {got}, declared {want}")

    # --- tilts ----------------------------------------------------------------
    background = view[view["population"] == "background"]
    keys = [tuple(bool(v) for v in row) for row in background[list(FLAGS)].to_numpy()]
    sizes: dict[tuple, int] = {}
    realised: dict[tuple, int] = {}
    for key, labelled in zip(keys, background["is_fraud"]):
        sizes[key] = sizes.get(key, 0) + 1
        realised[key] = realised.get(key, 0) + int(labelled)
    expected = _logistic_expectations(sizes, want["background"])
    worst = max(abs(realised[k] - expected[k]) for k in sizes)
    report.add("detection: every background stratum is within one claim of its expectation",
               worst < 1.0 + 1e-6, f"largest gap {worst:.3f} across {len(sizes)} strata")
    lifts = {}
    for flag in FLAGS:
        on, off = background[background[flag]], background[~background[flag]]
        lifts[flag] = (float(on["is_fraud"].mean()) if len(on) else 0.0, float(off["is_fraud"].mean()))
    detection["background_rate_flagged_vs_not"] = lifts
    # A flag that expects fewer than MIN_EXPECTED_FOR_DIRECTION labelled claims
    # rounds to zero, one or two: its marginal rate is noise, and the stratum
    # check above is its guarantee. Direction is asserted only where measurable.
    expected_flagged = {
        flag: sum(value for key, value in expected.items() if key[FLAGS.index(flag)])
        for flag in FLAGS
    }
    measurable = [flag for flag in FLAGS if expected_flagged[flag] >= MIN_EXPECTED_FOR_DIRECTION]
    detection["measurable_flags"] = measurable
    report.add("detection: every measurable behaviour flag raises the background rate",
               bool(measurable) and all(lifts[f][0] > lifts[f][1] for f in measurable),
               ", ".join(f"{f} {on:.1%} vs {off:.1%}" + ("" if f in measurable else " (too rare to assert)")
                         for f, (on, off) in lifts.items()))

    # --- tells ----------------------------------------------------------------
    present = [tells_in(t, l) for t, l in zip(view["note_text"], view["coverage_line"])]
    problems = []
    for tell, (rate_in, rate_out) in TELL_RATES.items():
        applies = np.array([_tell_applies(tell, l) for l in view["coverage_line"]])
        carries = np.array([tell in p for p in present])
        for is_labelled, rate in ((True, rate_in), (False, rate_out)):
            mask = applies & (view["is_fraud"].to_numpy() == is_labelled)
            if int(carries[mask].sum()) != exact_count(rate, int(mask.sum())):
                problems.append(f"{tell}/{'labelled' if is_labelled else 'rest'}: "
                                f"{int(carries[mask].sum())} vs {exact_count(rate, int(mask.sum()))}")
    report.add("detection: tell counts are exact in both classes", not problems, "; ".join(problems))

    # --- separability ---------------------------------------------------------
    score = reference_scores(view)
    measured = auc(score, view["is_fraud"].to_numpy())
    detection["reference_auc"] = measured
    report.add(f"detection: reference scorer AUC inside {AUC_BAND[0]:.2f}-{AUC_BAND[1]:.2f}",
               AUC_BAND[0] <= measured <= AUC_BAND[1], f"AUC {measured:.3f}")

    # --- rules-only proxy -----------------------------------------------------
    assignment = frames["scenario_assignment"]
    c5 = set(assignment.loc[assignment["scenario_id"] == "C5", "policy_id"])
    referred = (view["population"] == "S") | view["policy_id"].isin(c5)
    hits = int((referred & view["is_fraud"]).sum())
    recall = hits / max(int(view["is_fraud"].sum()), 1)
    precision = hits / max(int(referred.sum()), 1)
    detection["rules_proxy"] = {"recall": recall, "precision": precision}
    report.add("detection: scenario-membership proxy for the rules stays below its ceilings",
               recall <= PROXY_RECALL_CEILING and precision <= PROXY_PRECISION_CEILING,
               f"recall {recall:.3f} (<= {PROXY_RECALL_CEILING}), "
               f"precision {precision:.3f} (<= {PROXY_PRECISION_CEILING})")

    # --- leakage --------------------------------------------------------------
    labelled_text = " ".join(view.loc[view["is_fraud"], "note_text"])
    rest_text = " ".join(view.loc[~view["is_fraud"], "note_text"])
    exclusive = [p for p in all_phrases() if p in labelled_text and p not in rest_text]
    dirty = [t for t in view["note_text"] if _BANNED.search(t) or _POLICY_ID.search(t)]
    order = view.sort_values("claim_id")["is_fraud"].to_numpy(dtype=float)
    rho = float(np.corrcoef(np.arange(len(order)), order)[0, 1])
    detection["claim_id_rank_correlation"] = rho
    report.add("detection: no phrase is exclusive to labelled notes", not exclusive, "; ".join(exclusive[:3]))
    report.add("detection: notes carry no banned term and no policy-id lookalike", not dirty,
               f"{len(dirty)} offending notes")
    report.add("detection: the label is independent of claim_id order",
               abs(rho) < LEAKAGE_RANK_CORRELATION, f"rank correlation {rho:+.3f}")

    measurements["detection"] = detection


def summary_lines(measurements: dict) -> list[str]:
    detection = measurements.get("detection") or {}
    if "reference_auc" not in detection:
        return []
    proxy = detection["rules_proxy"]
    return [
        f"    labelled claims            {detection['labelled_by_population']} "
        f"of {detection['claims_by_population']}",
        f"    reference scorer AUC       {detection['reference_auc']:.3f} "
        f"(band {AUC_BAND[0]:.2f}-{AUC_BAND[1]:.2f}) - baseline for the evaluation bench",
        f"    rules proxy                recall {proxy['recall']:.3f}, precision {proxy['precision']:.3f}",
    ]
```

- [ ] **Step 3: Hook into `generator/validate.py`**

Add imports beside the existing `from .` imports:

```python
from . import truth, validate_truth
```

Change the signature `def run(out_dir: Path) -> tuple[Report, dict]:` to:

```python
def run(out_dir: Path, truth_dir: Path | None = None) -> tuple[Report, dict]:
```

Immediately before `run`'s final `return report, measurements` add:

```python
    # --- detection tables (ADR-0021) -----------------------------------------
    validate_truth.add_checks(
        report, measurements, frames, Path(truth_dir) if truth_dir else truth.default_dir(out_dir)
    )
```

In `main`, add the argument and pass it through:

```python
    parser.add_argument("--truth-out", default=None,
                        help="directory holding the evaluation-only table; defaults to <out>/eval")
```

```python
    report, measurements = run(Path(args.out), Path(args.truth_out) if args.truth_out else None)
```

and after the `print(f"    material changes derived …")` line add:

```python
    for line in validate_truth.summary_lines(measurements):
        print(line)
```

- [ ] **Step 4: Run; if a band check fails, stop and report — do not tune constants**

Run: `app/.venv/bin/python -m pytest generator/tests -q`

Expected: all PASS. The AUC was simulated at 0.85 (99% range 0.78–0.90 under *sampled* tells; exact allocation narrows it). If `test_other_seeds_also_pass` fails on the AUC band or a proxy ceiling, report the measured value to the user; the band is a declared design parameter and changing it is their decision.

Then print the real report once and keep the output for Task 8's docs:

```bash
app/.venv/bin/python -m generator --seed 42 --anchor-date 2026-01-01 --out /tmp/claude-ptm-raw
app/.venv/bin/python -m generator.validate --out /tmp/claude-ptm-raw | tail -30
```

- [ ] **Step 5: Commit**

```bash
git add generator/validate_truth.py generator/validate.py generator/tests/test_validate_truth.py
git commit -m "Generator validation: declared rates, strata, tells, separability band, leakage"
```

---

### Task 5: The vocabulary rule, scoped by surface

**Files:**
- Modify: `pipeline/transformations.py` (the `BANNED_VOCABULARY` block near line 114 and `vocabulary_violations` near line 462)
- Modify: `app/backend/review/vocabulary.py`, `ci/genie/ground_truth.py` (list near line 24)
- Test: `pipeline/tests/test_vocabulary_surfaces.py` (new), `app/backend/tests/test_review_vocabulary.py`

**Interfaces:**
- Produces (pipeline): `T.ACCUSATORY_TERMS`, `T.ALWAYS_BANNED`, `T.BANNED_VOCABULARY = ACCUSATORY_TERMS + ALWAYS_BANNED`, `T.SURFACES = ("investigation", "detector")`, `T.vocabulary_violations(text, surface="investigation", person_names=()) -> list[str]`.
- Produces (backend): `violations(text, own_policy_id=None, surface="investigation", person_names=())`, `is_clean(...)` with the same extra parameters.
- The detector surface returns the literal strings `"person as subject"` and `"person name"` for its two extra rules.

- [ ] **Step 1: Write the failing pipeline tests**

`pipeline/tests/test_vocabulary_surfaces.py`:

```python
"""ADR-0020: one banned list, two surfaces. The default surface is today's rule."""

import pytest

import transformations as T


def test_the_list_is_the_union_and_has_todays_members():
    assert T.BANNED_VOCABULARY == T.ACCUSATORY_TERMS + T.ALWAYS_BANNED
    assert set(T.BANNED_VOCABULARY) == {
        "fraud", "fraudulent", "suspicious", "scheme", "deceptive", "guilty",
        "risk score", "predicts", "causes", "leads to", "increases the risk of",
        "anomaly", "anomalous", "red flag",
    }
    assert "guilty" in T.ALWAYS_BANNED and "fraud" in T.ACCUSATORY_TERMS


@pytest.mark.parametrize("text", [
    "This looks suspicious.", "A red flag.", "It predicts a claim.", "Risk  score is high",
])
def test_the_default_surface_is_the_investigation_surface(text):
    assert T.vocabulary_violations(text) == T.vocabulary_violations(text, surface="investigation")
    assert T.vocabulary_violations(text)


def test_the_detector_surface_may_name_fraud_about_a_claim():
    assert T.vocabulary_violations(
        "This claim has a 0.82 probability of fraud.", surface="detector") == []
    assert T.vocabulary_violations(
        "Likely fraudulent claim; the note gives no location.", surface="detector") == []


def test_the_detector_surface_still_bans_causal_and_verdict_words():
    assert T.vocabulary_violations("A coverage raise predicts fraud.", surface="detector") == ["predicts"]
    assert T.vocabulary_violations("The claim is guilty.", surface="detector") == ["guilty"]


@pytest.mark.parametrize("text", [
    "The policyholder committed fraud.",
    "The insured is suspicious.",
    "A fraudulent claimant filed this.",
    "The driver staged the collision.",
])
def test_the_detector_surface_never_makes_a_person_the_subject(text):
    assert "person as subject" in T.vocabulary_violations(text, surface="detector")


def test_the_detector_surface_rejects_a_customer_name():
    found = T.vocabulary_violations(
        "Adele Ashcroft's claim is likely fraud.", surface="detector",
        person_names=("Adele Ashcroft",))
    assert found == ["person name"]


def test_an_unknown_surface_is_an_error():
    with pytest.raises(ValueError):
        T.vocabulary_violations("anything", surface="marketing")
```

Run: `cd pipeline && .venv/bin/python -m pytest tests/test_vocabulary_surfaces.py -q` — Expected: FAIL (`ACCUSATORY_TERMS` missing).

- [ ] **Step 2: Implement in `pipeline/transformations.py`**

Replace the `BANNED_VOCABULARY` tuple with:

```python
#: Terms that accuse. Banned on the investigation surface; permitted on the
#: detector surface, always about a claim and beside a probability (ADR-0020).
ACCUSATORY_TERMS: tuple[str, ...] = (
    "fraud", "fraudulent", "suspicious", "scheme", "deceptive",
    "risk score", "anomaly", "anomalous", "red flag",
)
#: Verdict and causal language. Banned on every surface (ADR-0014).
ALWAYS_BANNED: tuple[str, ...] = (
    "guilty", "predicts", "causes", "leads to", "increases the risk of",
)
BANNED_VOCABULARY: tuple[str, ...] = ACCUSATORY_TERMS + ALWAYS_BANNED

SURFACES: tuple[str, ...] = ("investigation", "detector")
```

Replace the `_BANNED_PATTERNS` construction and `vocabulary_violations` (keep the existing docstring's AMBIGUITY paragraph) with:

```python
def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE)


_BANNED_PATTERNS = tuple((term, _term_pattern(term)) for term in BANNED_VOCABULARY)
_ALWAYS_PATTERNS = tuple((term, _term_pattern(term)) for term in ALWAYS_BANNED)

_PERSON = r"(?:policyholder|customer|insured|claimant|driver)"
#: Fixed forms, not language understanding: they catch the obvious sentences and
#: the convention carries the rest (ADR-0020).
_PERSON_AS_SUBJECT: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\b{_PERSON}\b\s+(?:is|was|has|had)\b[^.]*?"
               r"\b(?:fraud\w*|suspicious|deceptive|dishonest|lying)\b", re.IGNORECASE),
    re.compile(rf"\b{_PERSON}\b\s+(?:committed|staged|lied|faked|invented)\b", re.IGNORECASE),
    re.compile(rf"\b(?:fraudulent|suspicious|deceptive|dishonest)\s+{_PERSON}\b", re.IGNORECASE),
)


def vocabulary_violations(
    text: Any, surface: str = "investigation", person_names: Sequence[str] = ()
) -> list[str]:
    """Violations of the vocabulary rule on one surface (E18, ADR-0020).

    ``investigation`` (the default, and the only surface the pipeline writes to)
    bans the whole list. ``detector`` permits the accusatory terms but never a
    person as their subject, never a customer's name, and never the verdict and
    causal terms.
    """
    if surface not in SURFACES:
        raise ValueError(f"unknown surface {surface!r}; expected one of {SURFACES}")
    value = to_str(text)
    if value is None:
        return []
    if surface == "investigation":
        return [term for term, pattern in _BANNED_PATTERNS if pattern.search(value)]
    found = [term for term, pattern in _ALWAYS_PATTERNS if pattern.search(value)]
    if any(pattern.search(value) for pattern in _PERSON_AS_SUBJECT):
        found.append("person as subject")
    if any(name and name.lower() in value.lower() for name in person_names):
        found.append("person name")
    return found
```

Check that `Sequence` is already imported from `typing` at the top of the file (it is used by `_densest_window`); if `_BANNED_PATTERNS` was previously built with a different helper, delete the old helper only if nothing else uses it.

Run: `cd pipeline && .venv/bin/python -m pytest -q` — Expected: all PASS (the new file and every existing E18 test).

- [ ] **Step 3: Mirror in the backend, with failing tests first**

Append to `app/backend/tests/test_review_vocabulary.py`:

```python
import ast


def test_detector_surface_may_name_fraud_but_not_a_person():
    assert violations("This claim has a 0.82 probability of fraud.", surface="detector") == []
    assert violations("Likely fraud on this claim.", surface="detector") == []   # 'likely' is allowed here
    assert "person as subject" in violations("The policyholder committed fraud.", surface="detector")
    assert violations("It predicts fraud.", surface="detector") == ["predicts"]
    assert violations("Adele Ashcroft's claim.", surface="detector",
                      person_names=("Adele Ashcroft",)) == ["person name"]


def test_detector_surface_still_rejects_another_policy_id():
    assert violations("Same shape as P-20114.", own_policy_id="P-10155",
                      surface="detector") == ["policy id P-20114"]


def test_ci_copy_of_the_banned_list_matches():
    """ci/genie/ground_truth.py imports the Databricks SDK, so read it with ast."""
    path = Path(__file__).resolve().parents[3] / "ci" / "genie" / "ground_truth.py"
    tree = ast.parse(path.read_text())
    values = [
        ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "BANNED_VOCABULARY" for t in node.targets)
    ]
    assert values and tuple(values[0]) == tuple(BANNED_VOCABULARY)
```

Run: `cd app && .venv/bin/python -m pytest backend/tests/test_review_vocabulary.py -q` — Expected: FAIL.

Rewrite `app/backend/review/vocabulary.py` below its docstring (extend the docstring with one sentence: "ADR-0020 scopes the list by surface; the Brief is investigation-surface."):

```python
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
```

- [ ] **Step 4: Align the ci copy**

In `ci/genie/ground_truth.py` replace the `BANNED_VOCABULARY = [...]` list with the same fourteen terms **in the same order** as `ACCUSATORY_TERMS + ALWAYS_BANNED`:

```python
BANNED_VOCABULARY = [
    "fraud", "fraudulent", "suspicious", "scheme", "deceptive",
    "risk score", "anomaly", "anomalous", "red flag",
    "guilty", "predicts", "causes", "leads to", "increases the risk of",
]
```

- [ ] **Step 5: Run all three suites and commit**

```bash
(cd pipeline && .venv/bin/python -m pytest -q)
(cd app && .venv/bin/python -m pytest backend/tests -q)
app/.venv/bin/python -m pytest generator/tests -q
```

Expected: all PASS.

```bash
git add pipeline/transformations.py pipeline/tests/test_vocabulary_surfaces.py \
        app/backend/review/vocabulary.py app/backend/tests/test_review_vocabulary.py ci/genie/ground_truth.py
git commit -m "Vocabulary rule scoped by surface; three copies of the list held together"
```

---

### Task 6: `claim_context` — transformation, key, expectations, comments

**Files:**
- Modify: `pipeline/transformations.py` (schema near line 170, `SCHEMAS`, `GOLD_KEYS`, a new builder after `build_claim_event`, `build_all`)
- Modify: `pipeline/expectations.py`, `pipeline/uc_comments.py`, `pipeline/dlt_pipeline.py` (`_build`, a new table after `claim_event`, a new QA table)
- Modify: `pipeline/tests/conftest.py` (`sources`, `curated`), `pipeline/tests/test_expectations.py`, `pipeline/tests/test_timeline_and_invariants.py`
- Test: `pipeline/tests/test_claim_context.py` (new)

**Interfaces:**
- Produces: `T.GENIE_SPACE_TABLES` (the six attached tables; `claim_context` is not among them); `T.CLAIM_CONTEXT_SCHEMA`; `T.RECENT_BEFORE_LOSS_DAYS = 30`; `T.build_claim_context(claims, policy_history, vehicle=None, claim_note=None) -> pd.DataFrame`; `T.build_all(..., vehicle=None, claim_note=None)` returning a seventh key `"claim_context"`; `X.claim_context() -> dict[str, str]`; `X.QA_CLAIM_CONTEXT_COVERAGE: dict[str, str]`; `all_expectations` keys `"claim_context"` and `"qa_claim_context_coverage"`.
- Column contract (spec §5.4): `claim_id, policy_id, policy_age_at_loss_days, prior_claims_count, days_since_prior_claim, reinstated_within_30d_before_loss, vehicle_added_within_30d_before_loss, note_text`.

- [ ] **Step 1: Write the failing transformation tests**

`pipeline/tests/test_claim_context.py`:

```python
"""claim_context: behaviour facts and the first-notice note, one row per claim."""

import datetime as _dt

import transformations as T

ANCHOR = _dt.date(2025, 6, 30)


def D(offset):
    return ANCHOR - _dt.timedelta(days=offset)


def version(policy_id, n, start, status="active"):
    return {"policy_id": policy_id, "version_no": n, "effective_from": start,
            "effective_to": _dt.date(9999, 12, 31), "is_current": False,
            "policy_status": status, "customer_id": "CUS-1"}


def claim(claim_id, policy_id, loss, report):
    return {"claim_id": claim_id, "policy_id": policy_id, "coverage_line": "COLL",
            "loss_date": loss, "report_date": report, "settled_amount": 1000.0,
            "claim_status": "settled"}


def by_id(frame):
    return {row["claim_id"]: row for row in T.records(frame)}


def test_schema_and_one_row_per_claim():
    out = T.build_claim_context(
        [claim("CLM-1", "P-10001", D(10), D(5))], [version("P-10001", 1, D(400))],
        [], [{"claim_id": "CLM-1", "note_text": "Caller reports a collision."}])
    assert list(out.columns) == [name for name, _ in T.CLAIM_CONTEXT_SCHEMA]
    row = by_id(out)["CLM-1"]
    assert row["policy_age_at_loss_days"] == 390
    assert row["prior_claims_count"] == 0 and row["days_since_prior_claim"] is None
    assert row["note_text"] == "Caller reports a collision."


def test_prior_claims_are_counted_on_report_date_not_loss_date():
    # CLM-B lost earlier but reported later, so CLM-A is its prior claim.
    claims = [claim("CLM-A", "P-10002", D(34), D(19)), claim("CLM-B", "P-10002", D(60), D(5))]
    rows = by_id(T.build_claim_context(claims, [version("P-10002", 1, D(500))], [], []))
    assert rows["CLM-A"]["prior_claims_count"] == 0
    assert rows["CLM-B"]["prior_claims_count"] == 1
    assert rows["CLM-B"]["days_since_prior_claim"] == 14


def test_reinstatement_window_is_inclusive_at_thirty_days_and_uses_entry_into_the_status():
    history = [version("P-10003", 1, D(500)), version("P-10003", 2, D(100), "lapsed"),
               version("P-10003", 3, D(80), "reinstated"), version("P-10003", 4, D(70), "reinstated")]
    claims = [claim("CLM-30", "P-10003", D(50), D(45)), claim("CLM-31", "P-10003", D(49), D(44)),
              claim("CLM-PRE", "P-10003", D(81), D(79))]
    rows = by_id(T.build_claim_context(claims, history, [], []))
    assert rows["CLM-30"]["reinstated_within_30d_before_loss"] is True     # exactly 30 days
    assert rows["CLM-31"]["reinstated_within_30d_before_loss"] is False    # 31 days
    assert rows["CLM-PRE"]["reinstated_within_30d_before_loss"] is False   # loss before it


def test_the_vehicle_a_policy_started_with_is_not_a_new_vehicle():
    history = [version("P-10004", 1, D(40))]
    vehicles = [{"vehicle_id": "VEH-1", "policy_id": "P-10004", "added_date": D(40)}]
    rows = by_id(T.build_claim_context([claim("CLM-1", "P-10004", D(20), D(15))], history, vehicles, []))
    assert rows["CLM-1"]["vehicle_added_within_30d_before_loss"] is False
    vehicles.append({"vehicle_id": "VEH-2", "policy_id": "P-10004", "added_date": D(20)})
    rows = by_id(T.build_claim_context([claim("CLM-1", "P-10004", D(20), D(15))], history, vehicles, []))
    assert rows["CLM-1"]["vehicle_added_within_30d_before_loss"] is True   # added on the loss date


def test_it_is_a_gold_table_keyed_on_the_claim():
    assert "claim_context" in T.SCHEMAS
    keys = T.GOLD_KEYS["claim_context"]
    assert keys.primary_key == ("claim_id",)
    assert [(fk.columns, fk.references_table) for fk in keys.foreign_keys] == [
        (("claim_id",), "claim_event"), (("policy_id",), "policy_profile")]


def test_build_all_returns_it(curated, claim_event):
    assert set(curated["claim_context"]["claim_id"]) == set(claim_event["claim_id"])
    assert curated["claim_context"]["note_text"].notna().all()
```

Run: `cd pipeline && .venv/bin/python -m pytest tests/test_claim_context.py -q` — Expected: FAIL (`build_claim_context` missing).

- [ ] **Step 2: Implement in `pipeline/transformations.py`**

After `CLAIM_EVENT_SCHEMA`:

```python
#: Behaviour facts and the first-notice note for one claim. Read by the detector
#: (sub-projects B-D); deliberately NOT part of the Genie space (ADR-0020).
CLAIM_CONTEXT_SCHEMA: tuple[tuple[str, str], ...] = (
    ("claim_id", "string"), ("policy_id", "string"), ("policy_age_at_loss_days", "int"),
    ("prior_claims_count", "int"), ("days_since_prior_claim", "int"),
    ("reinstated_within_30d_before_loss", "boolean"),
    ("vehicle_added_within_30d_before_loss", "boolean"),
    ("note_text", "string"),
)
RECENT_BEFORE_LOSS_DAYS = 30
```

Immediately above `SCHEMAS` add:

```python
#: The tables attached to the Genie space (ADR-0002). claim_context is published
#: to the same schema but deliberately left out (ADR-0020).
GENIE_SPACE_TABLES: tuple[str, ...] = (
    "policy_change_event", "claim_event", "policy_profile",
    "policy_timeline_event", "policy_pattern_match", "policy_similarity",
)
```

Add `"claim_context": CLAIM_CONTEXT_SCHEMA,` to `SCHEMAS` after `"claim_event"`, and to `GOLD_KEYS` (every gold table references `policy_profile`; `test_gold_keys.py` enforces it):

```python
    "claim_context": TableKeys(
        primary_key=("claim_id",),
        foreign_keys=(
            _fk("claim_context", ("claim_id",), "claim_event", ("claim_id",)),
            _fk("claim_context", ("policy_id",), "policy_profile", ("policy_id",)),
        ),
    ),
```

After `build_claim_event` (before the `policy_pattern_match` section banner):

```python
def _on_or_within_before(loss_date: _dt.date, dates: Sequence[_dt.date]) -> bool:
    return any(0 <= days_between(loss_date, d) <= RECENT_BEFORE_LOSS_DAYS for d in dates)


def build_claim_context(
    claims: Any, policy_history: Any, vehicle: Any = None, claim_note: Any = None
) -> pd.DataFrame:
    """One row per claim: tenure, claim history, recent policy events, the note.

    "Inception" is the first ``effective_from`` of the policy. A reinstatement is
    the version that *enters* the ``reinstated`` status, not every version that
    still carries it. A new vehicle is one added after inception, so the vehicle
    a policy started with never counts. Windows are 0..30 days before the Loss
    Date, inclusive at both ends.
    """
    starts = _policy_start_dates(policy_history)

    reinstated_on: dict[str, list[_dt.date]] = {}
    for policy_id, versions in _group_by(records(policy_history), "policy_id").items():
        previous = None
        for row in sorted(versions, key=lambda r: int(r.get("version_no") or 0)):
            status = to_str(row.get("policy_status"))
            entered = to_date(row.get("effective_from"))
            if status == "reinstated" and previous != "reinstated" and entered is not None:
                reinstated_on.setdefault(to_str(policy_id), []).append(entered)
            previous = status

    added_on: dict[str, list[_dt.date]] = {}
    for row in records(vehicle):
        policy_id = to_str(row.get("policy_id"))
        added, start = to_date(row.get("added_date")), starts.get(policy_id)
        if added is not None and start is not None and added > start:
            added_on.setdefault(policy_id, []).append(added)

    note_of = {to_str(r.get("claim_id")): to_str(r.get("note_text")) for r in records(claim_note)}

    out: list[dict[str, Any]] = []
    for policy_key, policy_claims in _group_by(records(claims), "policy_id").items():
        policy_id = to_str(policy_key)
        start = starts.get(policy_id)
        for source in policy_claims:
            claim_id = to_str(source.get("claim_id"))
            loss_date = to_date(source.get("loss_date"))
            report_date = to_date(source.get("report_date"))
            earlier_reports = sorted(
                to_date(c.get("report_date")) for c in policy_claims
                if report_date is not None and to_date(c.get("report_date")) is not None
                and to_date(c.get("report_date")) < report_date
            )
            out.append({
                "claim_id": claim_id,
                "policy_id": policy_id,
                "policy_age_at_loss_days": (
                    days_between(loss_date, start)
                    if loss_date is not None and start is not None else None
                ),
                "prior_claims_count": len(earlier_reports),
                "days_since_prior_claim": (
                    days_between(report_date, earlier_reports[-1]) if earlier_reports else None
                ),
                "reinstated_within_30d_before_loss": (
                    loss_date is not None
                    and _on_or_within_before(loss_date, reinstated_on.get(policy_id, []))
                ),
                "vehicle_added_within_30d_before_loss": (
                    loss_date is not None
                    and _on_or_within_before(loss_date, added_on.get(policy_id, []))
                ),
                "note_text": note_of.get(claim_id),
            })
    out.sort(key=lambda r: r["claim_id"] or "")
    return frame(out, CLAIM_CONTEXT_SCHEMA)
```

In `build_all`: add keyword parameters `vehicle: Any = None,` and `claim_note: Any = None,` after `claim_payment`; change the docstring's first line to "All seven curated tables, in dependency order."; build and return it:

```python
    claim_context = build_claim_context(claims, policy_history, vehicle, claim_note)
```

```python
        "claim_context": claim_context,
```

(insert after `"claim_event": claim_event,`).

- [ ] **Step 3: Fixtures**

In `pipeline/tests/conftest.py`, before the `anchor_date` fixture add:

```python
def _vehicles() -> list[dict]:
    """One vehicle per claimed policy, added at inception - so no fixture claim
    carries a new-vehicle flag; test_claim_context.py plants its own."""
    return []


def _claim_notes() -> list[dict]:
    return [
        {"claim_id": c["claim_id"],
         "note_text": "Caller reports a collision with another car while changing lanes. "
                      "Police attended and gave a reference number."}
        for c in _claims()
    ]
```

In `sources()` add `"vehicle": pd.DataFrame(_vehicles(), columns=["vehicle_id", "policy_id", "added_date"]),` and `"claim_note": pd.DataFrame(_claim_notes()),`. In `curated()` pass `vehicle=sources["vehicle"], claim_note=sources["claim_note"],`.

- [ ] **Step 4: Expectations — failing test first**

In `pipeline/tests/test_expectations.py`:

- in `test_every_dataset_has_a_catalogue` add `"qa_claim_context_coverage"` to the set literal;
- in `test_expectations_fail_the_run_rather_than_quarantining_rows` change `assert len(decorators) == 9` to `== 11` and its comment to "Seven curated tables plus the four cross-table assertion tables.";
- rename `test_all_twenty_numbered_expectations_are_enforced_somewhere` to `test_all_numbered_expectations_are_enforced_somewhere` and change both `range(1, 21)` to `range(1, 24)`;
- append:

```python
def test_claim_context_carries_the_vocabulary_and_identifier_guards():
    rules = CATALOGUE["claim_context"]
    assert "E18_note_text_uses_only_approved_vocabulary" in rules
    assert "E19_note_text_does_not_contain_a_policy_id" in rules
    assert "E22_note_text_is_present" in rules
    assert "E23_counts_and_tenure_are_never_negative" in rules
    assert "E21_every_claim_has_exactly_one_context_row" in CATALOGUE["qa_claim_context_coverage"]
```

Run — Expected: FAIL.

In `pipeline/expectations.py`, after `claim_event(...)`:

```python
def claim_context() -> dict[str, str]:
    return {
        # E18 — the note is investigation-surface text: Genie is not attached to
        # this table today, and must not be able to echo an accusation if it ever is.
        "E18_note_text_uses_only_approved_vocabulary": f"NOT (note_text RLIKE '{BANNED_RLIKE}')",
        # E19
        "E19_note_text_does_not_contain_a_policy_id": f"NOT (note_text RLIKE '{POLICY_ID_RLIKE}')",
        "E19_claim_id_does_not_look_like_a_policy_id": f"NOT (claim_id RLIKE '{POLICY_ID_RLIKE}')",
        "E19_policy_id_matches_the_policy_pattern": f"policy_id RLIKE '{POLICY_ID_RLIKE}'",
        # E22
        "E22_note_text_is_present": "note_text IS NOT NULL AND length(trim(note_text)) > 0",
        # E23
        "E23_counts_and_tenure_are_never_negative":
            "prior_claims_count >= 0 AND policy_age_at_loss_days >= 0 "
            "AND (days_since_prior_claim IS NULL OR days_since_prior_claim >= 0)",
        "prior_claim_gap_is_null_exactly_when_there_is_no_prior_claim":
            "(prior_claims_count = 0) = (days_since_prior_claim IS NULL)",
    }
```

Beside the other `QA_*` dicts:

```python
#: E21 — a full outer join of claim_event and claim_context on claim_id; a row
#: missing either side is a claim without context or context without a claim.
QA_CLAIM_CONTEXT_COVERAGE = {
    "E21_every_claim_has_exactly_one_context_row":
        "in_event IS NOT NULL AND in_context IS NOT NULL AND context_rows = 1",
}
```

In `all_expectations` add `"claim_context": claim_context(),` and `"qa_claim_context_coverage": QA_CLAIM_CONTEXT_COVERAGE,`. Update the module docstring's list: add a bullet "**E21–E23** — `claim_context`: coverage of `claim_event` (E21, a QA join), note present (E22), non-negative counts (E23)."

- [ ] **Step 5: Column comments**

In `pipeline/uc_comments.py::COMMENTS`, after the `"claim_event"` entry:

```python
    "claim_context": {
        None: (
            "One row per claim: how long the policy had run at the loss, the claim "
            "history before it, recent policy events, and the first-notice note. "
            "Join to claim_event on claim_id. Never use it for counting."
        ),
        "claim_id": "The claim this context belongs to. One row per claim_event row.",
        "policy_id": "The policy the claim was filed against.",
        "policy_age_at_loss_days": (
            "Days from the policy's inception (its first effective date) to loss_date."
        ),
        "prior_claims_count": (
            "Claims on the same policy with an earlier report_date."
        ),
        "days_since_prior_claim": (
            "Days from the latest earlier report_date on the policy to this claim's "
            "report_date. NULL for a policy's first claim."
        ),
        "reinstated_within_30d_before_loss": (
            "True when the policy entered reinstated status 0 to 30 days before loss_date."
        ),
        "vehicle_added_within_30d_before_loss": (
            "True when a vehicle was added after inception and 0 to 30 days before loss_date."
        ),
        "note_text": "The first-notice note taken when the loss was reported. Free text.",
    },
```

`_validate()` runs at import and applies the vocabulary rule to these strings.

- [ ] **Step 6: Pipeline wiring (`pipeline/dlt_pipeline.py`)** — in this task, because `test_gold_keys.py::test_pipeline_orders_fk_children_after_their_parents` reads this file's source

In `_build()`, after the `claim_payment = …` line add:

```python
    vehicle = _source("vehicle")
    claim_note = _source("claim_note")
```

and pass `vehicle=vehicle, claim_note=claim_note,` to `T.build_all(...)`.

After the `claim_event` table definition add:

```python
@dlt.table(
    name="claim_context",
    schema=_gold_schema_ddl("claim_context"),
    comment="One row per claim: tenure, claim history, recent policy events and "
            "the first-notice note. Read by the detector; not part of the Genie space.",
    table_properties={"quality": "gold"},
)
@dlt.expect_all_or_fail(EXPECTATIONS["claim_context"])
def claim_context():
    # FK parents — their PKs must exist before this flow declares the FKs
    dlt.read("policy_profile")
    dlt.read("claim_event")
    return _emit("claim_context")
```

After `qa_severity_agreement` add:

```python
@dlt.table(
    name="qa_claim_context_coverage",
    comment="E21 — claim_context holds exactly one row per claim_event row and no others.",
    temporary=True,
)
@dlt.expect_all_or_fail(X.QA_CLAIM_CONTEXT_COVERAGE)
def qa_claim_context_coverage():
    events = dlt.read("claim_event").select("claim_id", F.lit(True).alias("in_event"))
    context = (
        dlt.read("claim_context").groupBy("claim_id")
        .agg(F.count(F.lit(1)).alias("context_rows"))
        .withColumn("in_context", F.lit(True))
    )
    return events.join(context, "claim_id", "full_outer")
```

Update the module docstring and the QA banner comment wherever they say "six" gold tables: the Genie space still has six; the pipeline now publishes seven. Say exactly that.

- [ ] **Step 7: Update the one existing test that pins the curated set**

In `pipeline/tests/test_timeline_and_invariants.py` replace the body of `test_the_genie_space_is_exactly_six_tables` with:

```python
    assert set(T.GENIE_SPACE_TABLES) == {
        "policy_change_event", "claim_event", "policy_profile",
        "policy_timeline_event", "policy_pattern_match", "policy_similarity",
    }
    # claim_context is curated and published, but never attached to the space (ADR-0020).
    assert set(curated) - set(T.GENIE_SPACE_TABLES) == {"claim_context"}
```

- [ ] **Step 8: Run and commit**

Run: `cd pipeline && .venv/bin/python -m pytest -q` — Expected: all PASS.

```bash
git add pipeline/transformations.py pipeline/expectations.py pipeline/uc_comments.py pipeline/dlt_pipeline.py pipeline/tests/
git commit -m "Pipeline: claim_context gold table with E21-E23, keyed on the claim"
```

---

### Task 7: Hold the two derivations together; isolate the truth; wire the platform

**Files:**
- Create: `generator/tests/test_pipeline_agreement.py`, `generator/tests/test_truth_isolation.py`
- Modify: `workflow/generate_task.py`, `workflow/validate_task.py`, `workflow/load_source_tables.py`

**Interfaces:**
- Consumes: `T.build_claim_context`, `behaviour.claim_flags`, `truth.TABLE`.
- Platform layout: schema `workspace.ptm_eval`, volume `workspace.ptm_eval.raw`, table `workspace.ptm_eval.claim_fraud_truth`; bronze gains `workspace.ptm_bronze.claim_note`.

- [ ] **Step 1: Agreement test (generator facts == pipeline facts)**

`generator/tests/test_pipeline_agreement.py`:

```python
"""The label is allocated on generator.behaviour; the detector reads the pipeline's
claim_context. If the two derivations disagree, the planted signal is not the
signal an agent can see."""

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

from generator import build
from generator.behaviour import claim_flags


def _transformations():
    path = Path(__file__).resolve().parents[2] / "pipeline" / "transformations.py"
    spec = importlib.util.spec_from_file_location("ptm_transformations", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"pipeline module not importable here: {exc}")
    return module


def test_behaviour_facts_agree_with_claim_context():
    T = _transformations()
    frames = build(42, dt.datetime.now(dt.timezone.utc).date())
    context = T.build_claim_context(
        frames["claim"], frames["policy_history"], frames["vehicle"], frames["claim_note"]
    ).set_index("claim_id")
    facts = claim_flags(frames).set_index("claim_id")
    assert set(context.index) == set(facts.index)
    context = context.loc[facts.index]
    assert (context["policy_age_at_loss_days"].astype(int) == facts["policy_age_at_loss_days"]).all()
    assert (context["reinstated_within_30d_before_loss"].astype(bool) == facts["recent_reinstatement"]).all()
    assert (context["vehicle_added_within_30d_before_loss"].astype(bool) == facts["new_vehicle"]).all()
    assert (context["note_text"] == frames["claim_note"].set_index("claim_id")["note_text"]).all()
```

Run: `app/.venv/bin/python -m pytest generator/tests/test_pipeline_agreement.py -q` — Expected: PASS. A failure here is a real disagreement between Task 1 and Task 6; fix the derivation that departs from spec §5.2's definitions, not the test.

- [ ] **Step 2: Isolation test**

`generator/tests/test_truth_isolation.py`:

```python
"""Spec section 5.5: no product surface and no agent may be able to name the truth.

The application, the pipeline and the documents that define the Genie space must
never mention the truth table, its schema or its column."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("claim_fraud_truth", "ptm_eval", "is_fraud")
GUARDED_DIRS = ("app/backend", "app/frontend/src", "pipeline")
GUARDED_FILES = ("app/app.yaml", "docs/genie-curation.md", "docs/specs/03-genie-knowledge.md")
SUFFIXES = {".py", ".js", ".jsx", ".json", ".yaml", ".yml", ".md", ".sql", ".css"}


def _offenders():
    paths = [ROOT / f for f in GUARDED_FILES if (ROOT / f).exists()]
    for directory in GUARDED_DIRS:
        paths += [p for p in (ROOT / directory).rglob("*")
                  if p.is_file() and p.suffix in SUFFIXES
                  and "node_modules" not in p.parts and ".venv" not in p.parts]
    for path in paths:
        text = path.read_text(errors="ignore")
        for term in FORBIDDEN:
            if term in text:
                yield f"{path.relative_to(ROOT)}: {term}"


def test_the_truth_is_never_named_where_the_product_or_genie_can_see_it():
    assert not list(_offenders())
```

Run — Expected: PASS.

- [ ] **Step 3: Workflow wiring**

`workflow/generate_task.py`: add `TRUTH_DIR = f"/Volumes/{CATALOG}/ptm_eval/raw"`; append to `MEDALLION_DDL`:

```python
    # ADR-0021: the evaluation-only truth lives outside the medallion schemas,
    # in a schema the application and the Genie space are never granted.
    f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.ptm_eval",
    f"CREATE VOLUME IF NOT EXISTS {CATALOG}.ptm_eval.raw",
```

and change the generator call to:

```python
    return generator_main([
        "--seed", str(SEED), "--anchor-date", anchor, "--out", OUT_DIR, "--truth-out", TRUTH_DIR,
    ])
```

`workflow/validate_task.py`: add `TRUTH_DIR = "/Volumes/workspace/ptm_eval/raw"` and call `validate_main(["--out", OUT_DIR, "--truth-out", TRUTH_DIR])`; extend the docstring's list of what validation answers with "and that the planted truth holds its declared rates, tells and separability band (ADR-0021)".

`workflow/load_source_tables.py`: append `"claim_note",` to `TABLES` (update the "nine" wording in the docstring and comment to "ten"), and after the loop in `main()` add:

```python
    # The evaluation-only table: its own schema, its own volume (ADR-0021).
    truth_path = "/Volumes/workspace/ptm_eval/raw/claim_fraud_truth.parquet"
    truth_table = f"{CATALOG}.ptm_eval.claim_fraud_truth"
    print(f"[load_source_tables] {truth_table} <- {truth_path}")
    spark.sql(f"CREATE OR REPLACE TABLE {truth_table} AS SELECT * FROM parquet.`{truth_path}`")
    print(f"  {spark.table(truth_table).count():,} rows")
```

- [ ] **Step 4: Run everything and commit**

```bash
app/.venv/bin/python -m pytest generator/tests -q
(cd pipeline && .venv/bin/python -m pytest -q)
(cd app && .venv/bin/python -m pytest backend/tests -q)
databricks bundle validate   # if the CLI is authenticated; otherwise note it as not run
```

```bash
git add generator/tests/test_pipeline_agreement.py generator/tests/test_truth_isolation.py \
        workflow/generate_task.py workflow/validate_task.py workflow/load_source_tables.py
git commit -m "Platform wiring: claim_context published, truth loaded into ptm_eval, isolation enforced"
```

---

### Task 8: Documents

**Files:**
- Create: `docs/adr/0020-fraud-detection-lives-on-a-fenced-detector-surface.md`, `docs/adr/0021-fraud-truth-is-conditional-on-existing-behaviour-and-held-outside-the-medallion-schemas.md`
- Modify: `docs/specs/09-product-charter.md` (the "Not a fraud detection engine…" paragraph and the one after it), `CONTEXT.md`, `docs/specs/01-data-model-and-synthetic-data.md`, `docs/specs/02-semantic-layer.md`, `docs/specs/08-test-strategy.md`, `docs/adr/0016-the-catalog-follows-medallion-schemas.md`, `docs/development.md` (if it lists generator outputs)

Read two existing ADRs first (`docs/adr/0014-…`, `docs/adr/0019-…`) and match their form: a title sentence, the decision in a paragraph, the tension, then `## Consequences` bullets. No status headers, no dates.

- [ ] **Step 1: ADR-0020.** Must state: the decision (the product now estimates the probability that a claim is fraudulent, on a named detector surface); what it supersedes (the charter's "not a fraud detection engine, not a fraud score"); why scoped rather than lifted (the investigation surface's guarantees — associational language, named rules, no characterisation of a person — are what ADR-0009/0014/0018 rest on and they still hold there); the alternatives rejected (lift the vocabulary everywhere; score internally but keep soft words in the UI). Consequences: the list split and the `surface` parameter defaulting to investigation; the person-subject rule is fixed regular expressions, not language understanding; `ALWAYS_BANNED` on every surface; the Verdict is a separate artefact, not a Brief section; the human Disposition remains the only decision on record; the generator's source-vocabulary test exempts exactly `truth.py` and `validate_truth.py`.

- [ ] **Step 2: ADR-0021.** Must state: the label is allocated conditional on behaviour that already exists, because existing tables must stay byte-identical (the fifteen contracts and ADR-0014's calibration depend on them); the measured book (1,285 claims: 150 S, 135 C, 1,000 background; no behaviour variance inside S) and what follows (S flat at 40%, background 3% tilted, the note is the only separating evidence inside the rule-matched group); exact allocation rather than sampling; the truth lives in `ptm_eval`, outside the medallion schemas of ADR-0016, because bronze is reachable by an agent run (the app service principal is granted gold only, but the nightly `build_briefs` task runs the harness as the Workflow's run-as identity, which reads bronze), and a schema of its own cannot be exposed by a later bronze grant; alternatives rejected (separate F scenarios; model-written notes; growing the book). Consequences: every check in spec §6; the isolation test; `claim_context` kept out of the Genie space until a contract re-run says otherwise.

- [ ] **Step 3: Charter.** Replace the sentence "Not a fraud detection engine. Not a fraud score." with wording that keeps the rest of the list: the product is not underwriting, pricing or adjudication, not a general dashboard, SQL chatbot or policy administration system. Add one paragraph: it investigates policy history and, on a fenced detector surface (ADR-0020), estimates the probability that a claim is fraudulent — always about a claim, always beside a probability, never about a person; the reviewer's Disposition is the only decision on record. In the following paragraph, qualify "A fixed vocabulary governs every user-facing string" with "on the investigation surface".

- [ ] **Step 4: `CONTEXT.md`.** Add, before "## Flagged ambiguities", a `### Detection` section defining **Investigation surface**, **Detector surface**, **Fraud Truth**, **Sweep Score**, **Verdict**, **Case File** with the definitions from spec §4.2 (each with an `_Avoid_` line where one helps: Verdict — _Avoid_: decision, disposition; Fraud Truth — _Avoid_: label (in product copy), ground truth score). Append "(on the investigation surface)" to the `_Avoid_` lines of Noteworthy Pattern, Investigation Candidate, Routed Claim and Routing Rule.

- [ ] **Step 5: Spec 01.** Add `claim_note { string claim_id PK/FK; string note_text }` to the ER diagram and a note that `claim_fraud_truth { claim_id, is_fraud, population }` is emitted apart from the source tables. Add a §9 subsection "Fraud truth and planted evidence" carrying **every** declared parameter from this plan's Global Constraints, the measured population table, the three flag definitions, the tell table, the note rules (spec §5.3), and the validation checks with their thresholds. Paste the detection lines from the validation report captured in Task 4 Step 4 as the measured values. In §11 state that the vocabulary constraint applies to the investigation surface and that note phrase pools are bound by it.

- [ ] **Step 6: Spec 02, spec 08, ADR-0016.** Spec 02: a `claim_context` section (columns, definitions, "not attached to the Genie space") and E21–E23 in the expectations table. Spec 08: rows for the generator detection checks, the byte-identity test, the agreement test, the isolation test, the vocabulary-surface tests. ADR-0016: one consequence bullet — `ptm_eval` exists outside the medallion schemas for evaluation-only data (ADR-0021).

- [ ] **Step 7: Check and commit**

```bash
app/.venv/bin/python -m pytest generator/tests/test_truth_isolation.py -q
```

Read the new ADRs, `CONTEXT.md` and the charter once against the Wording constraint. Expected: isolation test PASS (the guarded Genie documents were not edited to name the truth).

```bash
git add docs/ CONTEXT.md
git commit -m "Docs: ADR-0020 detector surface, ADR-0021 fraud truth; charter, glossary, specs 01/02/08"
```

---

### Task 9: Live verification (needs the user's workspace)

These steps create nothing billable beyond a normal regeneration, but they need an authenticated CLI. If `databricks auth describe` fails, stop and hand this task to the user as a checklist.

- [ ] **Step 1:** `databricks bundle validate && databricks bundle deploy`
- [ ] **Step 2:** Run the regeneration job: `databricks bundle run policy_time_machine_regeneration`. Expected: `generate`, `validate`, `load_source_tables`, `refresh_pipeline` all succeed; the `validate` task log shows every `detection:` check as PASS and prints the reference AUC and the rules proxy.
- [ ] **Step 3:** Confirm the layout with the SQL warehouse:

```sql
SELECT population, count(*) AS claims, sum(CAST(is_fraud AS INT)) AS labelled
FROM workspace.ptm_eval.claim_fraud_truth GROUP BY population;
SELECT count(*) FROM workspace.ptm_gold.claim_context;          -- equals claim_event
SHOW GRANTS ON SCHEMA workspace.ptm_eval;                        -- the app service principal is absent
```

- [ ] **Step 4:** Run the fifteen Genie contracts (`python -m ci.genie.run_contracts`, from the environment described in `docs/development.md`). Expected: 3/3 on all fifteen, assertions unchanged. `claim_context` is not attached to the space, so any regression here is a finding to report, not to patch around.
- [ ] **Step 5:** Record the outcome of Steps 2–4 in the PR description. Definition of done is spec §9.

---

## Self-Review Notes

- **Verified in a scratch copy (2026-09-17):** Tasks 1–4 applied to `generator/` pass all 51 generator tests on seeds 42, 7 and 1234 (reference AUC 0.855–0.859; rules proxy recall 0.667, precision 0.38–0.39; byte identity holds). Tasks 5–6 applied to `pipeline/` pass the pipeline suite, and the generator and pipeline derivations agree on every claim.

- **Spec coverage:** §4 → Tasks 5, 8; §5.2 → Tasks 1, 3; §5.3 → Task 2; §5.4 → Task 6; §5.5 → Tasks 3 (separate directory), 7 (schema, volume, isolation test); §6 → Task 4; §7 → tests in every task; §8 → Task 8; §9 → Task 9.
- **Deviation from the spec, deliberate:** the validator's tilt check asserts "within one claim of the logistic expectation" and the truth table carries `population`; both are already reflected in the committed spec.
- **Known judgement call:** `_vehicles()` in the pipeline fixtures is empty on purpose; `test_claim_context.py` plants its own vehicles so the shared fixture's eleven stories stay untouched.
