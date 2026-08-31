"""Solve the claim hazard so that measured effects equal the declared ones.

The declared effect sizes in spec 01 section 8 are design parameters, and the
generator has to *hit* them rather than hope for them. Two things make that
possible:

1. Every policy-day carries a state code recording which exposure windows it
   sits inside — within 90 days of any material change (the headline axis) and
   within 60 days of a material change of each of the five categories (the
   ranking axis). There are at most 64 such codes, so the entire portfolio
   collapses to a 64-bin problem.
2. Background claims are allocated **exactly** rather than drawn independently.
   Once the per-state claim counts are fixed, the measured rates are fixed too,
   so the category ranking is a property of the construction rather than a
   sample from a distribution. The ranking of 1.15 against 1.05 could not
   survive Bernoulli noise at this dataset size, and the ranking is the part of
   the specification that must not move.

Scenario and control populations are folded into the solve as fixed, already
placed claims, so the background is calibrated *around* them. That is what keeps
the control populations load-bearing: C2's changes with no claims genuinely drag
the exposed rate down, and the solver has to make up the difference elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (
    EXPOSURE_KEY_LIFTS,
    EXPOSURE_KEYS,
    RATE_NO_RECENT_MATERIAL_CHANGE,
    RATE_RECENT_MATERIAL_CHANGE,
)

KEYS = tuple(EXPOSURE_KEYS)
N_STATES = 1 << (1 + len(KEYS))
DAYS_PER_YEAR = 365.0

STATE_CODES = np.arange(N_STATES)
BIT_RECENT = 1
KEY_BITS = {name: 1 << (i + 1) for i, name in enumerate(KEYS)}


@dataclass
class HazardSolution:
    base_daily: float
    recent_multiplier: float
    key_multipliers: dict[str, float]
    expected_by_state: np.ndarray
    counts_by_state: np.ndarray
    residual: float


def state_code(recent90: np.ndarray, within60: dict[str, np.ndarray]) -> np.ndarray:
    code = recent90.astype(np.int32) * BIT_RECENT
    for name, bit in KEY_BITS.items():
        code = code + within60[name].astype(np.int32) * bit
    return code


def _region_masks() -> dict[str, np.ndarray]:
    masks = {
        "unexposed_90": (STATE_CODES & BIT_RECENT) == 0,
        "exposed_90": (STATE_CODES & BIT_RECENT) != 0,
        "unexposed_60": (STATE_CODES >> 1) == 0,
    }
    for name, bit in KEY_BITS.items():
        masks[name] = (STATE_CODES & bit) != 0
    return masks


def _hazard(base: float, recent: float, multipliers: dict[str, float]) -> np.ndarray:
    hz = np.full(N_STATES, base, dtype=float)
    hz[(STATE_CODES & BIT_RECENT) != 0] *= recent
    for name, bit in KEY_BITS.items():
        hz[(STATE_CODES & bit) != 0] *= multipliers[name]
    return hz


def largest_remainder(values: np.ndarray) -> np.ndarray:
    """Round a vector of expected counts to integers, preserving the total."""
    floor = np.floor(values).astype(np.int64)
    remainder = values - floor
    shortfall = int(round(values.sum())) - int(floor.sum())
    if shortfall > 0:
        order = np.argsort(-remainder, kind="stable")[:shortfall]
        floor[order] += 1
    return floor


def solve(
    exposure_days_by_state: np.ndarray,
    eligible_days_by_state: np.ndarray,
    planted_claims_by_state: np.ndarray,
    iterations: int = 400,
) -> HazardSolution:
    """Fit the daily claim hazard to the declared rates and category lifts.

    ``exposure_days_by_state`` is the denominator (all policy-days on the books).
    ``eligible_days_by_state`` is where a background claim may actually be
    placed; scenario windows and the never-claimed control population are
    excluded there but still count as exposure, which is the point of them.
    """
    masks = _region_masks()
    exposure_years = {
        name: exposure_days_by_state[mask].sum() / DAYS_PER_YEAR for name, mask in masks.items()
    }
    planted = {name: planted_claims_by_state[mask].sum() for name, mask in masks.items()}

    for name, years in exposure_years.items():
        if years <= 0:
            raise ValueError(f"no exposure in region {name!r}; cannot calibrate")

    base = RATE_NO_RECENT_MATERIAL_CHANGE / DAYS_PER_YEAR
    recent = RATE_RECENT_MATERIAL_CHANGE / RATE_NO_RECENT_MATERIAL_CHANGE
    cats = dict(EXPOSURE_KEY_LIFTS)

    def expected(hz: np.ndarray, mask: np.ndarray) -> float:
        return float((eligible_days_by_state * hz)[mask].sum())

    residual = float("inf")
    for _ in range(iterations):
        # 1. The unexposed-90 region sees only the base hazard, so it solves in
        #    one step given the claims already planted there.
        hz = _hazard(base, recent, cats)
        want = RATE_NO_RECENT_MATERIAL_CHANGE * exposure_years["unexposed_90"] - planted["unexposed_90"]
        have = expected(hz, masks["unexposed_90"])
        base *= _ratio(want, have)

        # 2. The exposed-90 region scales linearly in the recent multiplier.
        hz = _hazard(base, recent, cats)
        want = RATE_RECENT_MATERIAL_CHANGE * exposure_years["exposed_90"] - planted["exposed_90"]
        have = expected(hz, masks["exposed_90"])
        recent *= _ratio(want, have)

        # 3. Each exposure region scales linearly in its own multiplier. The
        #    reference rate is the no-material-change-in-60-days population,
        #    which contains none of those multipliers.
        hz = _hazard(base, recent, cats)
        reference = (planted["unexposed_60"] + expected(hz, masks["unexposed_60"])) / exposure_years[
            "unexposed_60"
        ]
        for name in KEYS:
            hz = _hazard(base, recent, cats)
            want = EXPOSURE_KEY_LIFTS[name] * reference * exposure_years[name] - planted[name]
            have = expected(hz, masks[name])
            cats[name] *= _ratio(want, have)

        residual = _residual(base, recent, cats, eligible_days_by_state, exposure_years, planted, masks)
        if residual < 1e-9:
            break

    if residual > 1e-4:
        raise RuntimeError(
            f"claim hazard calibration did not converge (residual {residual:.3g}); "
            "the planted populations are probably too large for the declared rates"
        )

    hz = _hazard(base, recent, cats)
    expected_by_state = eligible_days_by_state * hz
    counts = _exact_region_counts(
        expected_by_state, eligible_days_by_state, exposure_years, planted, masks
    )
    over = counts > eligible_days_by_state
    if over.any():
        raise RuntimeError("more background claims allocated than eligible policy-days in a state")

    return HazardSolution(
        base_daily=base,
        recent_multiplier=recent,
        key_multipliers=dict(cats),
        expected_by_state=expected_by_state,
        counts_by_state=counts,
        residual=residual,
    )


def _exact_region_counts(
    expected: np.ndarray,
    eligible: np.ndarray,
    exposure_years: dict[str, float],
    planted: dict[str, float],
    masks: dict[str, np.ndarray],
) -> np.ndarray:
    """Make every region's claim count exactly the declared one.

    Rounding 256 expected values independently leaves each region a couple of
    claims off, which is nothing next to the headline comparison and fatal next
    to the vehicle-versus-status ordering: they are declared eight percent
    apart and carry a few dozen claims each.

    The state codes make the repair easy. Every category bit implies the
    ninety-day bit, so `unexposed_90` is exactly state 0 and `unexposed_60` is
    exactly states 0 and 1. Each exposure key has exactly one *pure* state -
    recent, that key, nothing else - which is the largest state in its region
    and belongs to no other key's region. Nudging those eight states lands every
    region on its target without disturbing the others.
    """
    counts = largest_remainder(expected)
    pure = {key: BIT_RECENT | bit for key, bit in KEY_BITS.items()}

    def clip(state: int, value: float) -> int:
        return int(min(max(round(value), 0), eligible[state]))

    counts[0] = clip(
        0, RATE_NO_RECENT_MATERIAL_CHANGE * exposure_years["unexposed_90"] - planted["unexposed_90"]
    )
    for _ in range(40):
        reference = (planted["unexposed_60"] + counts[0] + counts[1]) / exposure_years["unexposed_60"]
        for key in KEYS:
            want = EXPOSURE_KEY_LIFTS[key] * reference * exposure_years[key] - planted[key]
            have = counts[masks[key]].sum()
            counts[pure[key]] = clip(pure[key], counts[pure[key]] + round(want) - have)
        want = RATE_RECENT_MATERIAL_CHANGE * exposure_years["exposed_90"] - planted["exposed_90"]
        have = counts[masks["exposed_90"]].sum()
        previous = counts[1]
        counts[1] = clip(1, counts[1] + round(want) - have)
        if counts[1] == previous:
            break
    return counts


def _ratio(want: float, have: float) -> float:
    if have <= 0:
        raise RuntimeError("a calibration region has no eligible policy-days")
    if want <= 0:
        raise RuntimeError(
            "planted claims already exceed the declared rate for a region; "
            "reduce the scenario populations or raise the declared rate"
        )
    return want / have


def _residual(base, recent, cats, eligible, exposure_years, planted, masks) -> float:
    hz = _hazard(base, recent, cats)
    rate = {
        name: (planted[name] + float((eligible * hz)[mask].sum())) / exposure_years[name]
        for name, mask in masks.items()
    }
    errors = [
        rate["unexposed_90"] / RATE_NO_RECENT_MATERIAL_CHANGE - 1.0,
        rate["exposed_90"] / RATE_RECENT_MATERIAL_CHANGE - 1.0,
    ]
    for name, lift in EXPOSURE_KEY_LIFTS.items():
        errors.append((rate[name] / rate["unexposed_60"]) / lift - 1.0)
    return float(np.abs(errors).max())
