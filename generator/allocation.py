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
