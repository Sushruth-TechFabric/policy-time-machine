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
