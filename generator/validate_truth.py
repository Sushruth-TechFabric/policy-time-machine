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
