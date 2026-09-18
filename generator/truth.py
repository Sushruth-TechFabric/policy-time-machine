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
