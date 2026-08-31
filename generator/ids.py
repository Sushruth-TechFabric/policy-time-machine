"""Identifier minting and the lexical reservation check (spec 01 section 2).

Identifiers derive from the seed alone (ADR-0006): `P-18492` is the same policy
with the same story at every anchor date.

The lexical reservation is the load-bearing rule here. The application detects
policy references in question text with ``\\bP-\\d{5}\\b`` (ADR-0007), so any
other identifier that happens to contain that substring would silently route a
timeline to the wrong place. It is asserted at emit time, and a violation is a
build failure rather than a warning.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .constants import ID_FORMATS, POLICY_REFERENCE_PATTERN

_POLICY_RE = re.compile(POLICY_REFERENCE_PATTERN, re.IGNORECASE)


def mint(kind: str, count: int, rng: np.random.Generator) -> np.ndarray:
    """Mint ``count`` distinct identifiers of ``kind`` from a seeded stream.

    Rejection sampling rather than a full permutation: the eight-digit spaces
    hold ninety million values and materialising them would cost more memory
    than the whole dataset.
    """
    prefix, width = ID_FORMATS[kind]
    low = 10 ** (width - 1)
    span = 10**width - low
    if count > span:
        raise ValueError(f"cannot mint {count} distinct {kind} identifiers in {width} digits")
    picks = np.empty(0, dtype=np.int64)
    while picks.size < count:
        draw = rng.integers(0, span, size=max(count - picks.size, 16) * 2)
        picks = np.unique(np.concatenate([picks, draw]))
    picks = picks[:count] + low
    # Shuffle so identifier order carries no information about row order.
    rng.shuffle(picks)
    return np.array([f"{prefix}{value:0{width}d}" for value in picks], dtype=object)


def contains_policy_reference(value: str) -> bool:
    return bool(_POLICY_RE.search(value))


def assert_lexical_reservation(
    frames: dict[str, pd.DataFrame],
    policy_columns: set[str],
) -> None:
    """Fail if any non-policy string value contains a policy reference.

    Every string column of every emitted table is scanned. Columns listed in
    ``policy_columns`` are the only ones permitted to match, and they are also
    checked for the opposite failure: a policy identifier that does *not* match
    would be equally invisible to the application's detector.
    """
    problems: list[str] = []
    for table, frame in frames.items():
        for column in frame.columns:
            series = frame[column]
            if series.dtype != object:
                continue
            values = series.dropna().unique()
            if column in policy_columns:
                bad = [v for v in values if isinstance(v, str) and not contains_policy_reference(v)]
                if bad:
                    problems.append(
                        f"{table}.{column}: policy column holds undetectable values, e.g. {bad[:3]}"
                    )
                continue
            bad = [v for v in values if isinstance(v, str) and contains_policy_reference(v)]
            if bad:
                problems.append(
                    f"{table}.{column}: non-policy value matches the policy pattern, e.g. {bad[:3]}"
                )
    if problems:
        raise AssertionError("lexical reservation violated:\n  " + "\n  ".join(problems))
