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
