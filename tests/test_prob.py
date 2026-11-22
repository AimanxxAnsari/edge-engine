import math
from fractions import Fraction

import pytest

from edge_engine.prob import (
    binomial_cdf,
    binomial_pmf,
    hypergeometric_cdf,
    hypergeometric_mean,
    hypergeometric_pmf,
    hypergeometric_variance,
    monte_carlo,
    n_choose_k,
)
from edge_engine.rng import Rng


def test_n_choose_k_matches_math_comb():
    for n in range(0, 40):
        for k in range(-1, n + 2):
            expected = math.comb(n, k) if 0 <= k <= n else 0
            assert n_choose_k(n, k) == expected


def test_n_choose_k_known_values():
    assert n_choose_k(52, 5) == 2_598_960
    assert n_choose_k(52, 2) == 1326
    with pytest.raises(ValueError):
        n_choose_k(-1, 0)


def test_binomial_exact():
    # Four heads in ten flips of a 60% coin.
    p = Fraction(3, 5)
    assert binomial_pmf(4, 10, p) == 210 * p**4 * (1 - p) ** 6
    assert sum(binomial_pmf(k, 10, p) for k in range(11)) == 1
    assert binomial_cdf(10, 10, p) == 1
    assert binomial_pmf(11, 10, p) == 0
    assert binomial_pmf(0, 3, Fraction(1, 2)) == Fraction(1, 8)


def test_binomial_float_and_errors():
    assert binomial_cdf(1, 2, 0.5) == pytest.approx(0.75)
    with pytest.raises(ValueError):
        binomial_pmf(1, 2, 1.5)


def test_hypergeometric_known_values():
    # Exactly one ace in a five-card hand.
    assert hypergeometric_pmf(1, 52, 4, 5) == Fraction(4 * 194580, 2598960)
    total = sum(hypergeometric_pmf(k, 52, 4, 5) for k in range(5))
    assert total == 1
    assert hypergeometric_cdf(4, 52, 4, 5) == 1
    # Flush draw: P(no club in 2 cards from 47 unseen with 9 clubs).
    assert hypergeometric_pmf(0, 47, 9, 2) == Fraction(38 * 37, 47 * 46)


def test_hypergeometric_moments_match_pmf():
    N, K, n = 20, 7, 5
    pmf = [hypergeometric_pmf(k, N, K, n) for k in range(n + 1)]
    mean = sum(k * p for k, p in enumerate(pmf))
    var = sum((k - mean) ** 2 * p for k, p in enumerate(pmf))
    assert mean == hypergeometric_mean(N, K, n)
    assert var == hypergeometric_variance(N, K, n)


def test_monte_carlo_dice_within_standard_error():
    def trial(rng):
        return float(rng.randint(1, 6) + rng.randint(1, 6) >= 9)

    res = monte_carlo(trial, 20_000, Rng(1))
    p = 10 / 36
    assert abs(res.mean - p) < 4 * res.std_err
    assert res.std_err == pytest.approx(math.sqrt(p * (1 - p) / 20_000), rel=0.05)
    lo, hi = res.ci()
    assert lo < res.mean < hi


def test_monte_carlo_constant_and_reproducible():
    res = monte_carlo(lambda rng: 3.0, 10, Rng(0))
    assert res.mean == 3.0 and res.std_err == 0.0
    a = monte_carlo(lambda rng: rng.random(), 100, Rng(5))
    b = monte_carlo(lambda rng: rng.random(), 100, Rng(5))
    assert a == b
    with pytest.raises(ValueError):
        monte_carlo(lambda rng: 0.0, 1, Rng(0))
