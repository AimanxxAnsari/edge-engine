"""Exact probability helpers and a Monte Carlo runner with standard error."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from numbers import Real

from .rng import Rng


def n_choose_k(n: int, k: int) -> int:
    """Number of ways to choose k items from n, as an exact integer.

    Multiplicative formula: after step i the running value equals C(n-k+i, i),
    so the integer division is always exact.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    r = 1
    for i in range(1, k + 1):
        r = r * (n - k + i) // i
    return r


def _check_p(p: Real) -> None:
    if not 0 <= p <= 1:
        raise ValueError("p must be in [0, 1]")


def binomial_pmf(k: int, n: int, p: Real) -> Real:
    """P(X = k) for X ~ Binomial(n, p). Exact if p is a Fraction."""
    _check_p(p)
    if k < 0 or k > n:
        return 0 * p
    return n_choose_k(n, k) * p**k * (1 - p) ** (n - k)


def binomial_cdf(k: int, n: int, p: Real) -> Real:
    """P(X <= k) for X ~ Binomial(n, p)."""
    _check_p(p)
    total = 0 * p
    for i in range(0, min(k, n) + 1):
        total += binomial_pmf(i, n, p)
    return total


def hypergeometric_pmf(k: int, population: int, successes: int, draws: int) -> Fraction:
    """P(X = k): k successes in `draws` draws without replacement.

    population = N items in total, successes = K of them are successes.
    Returns an exact Fraction.
    """
    if not 0 <= successes <= population or not 0 <= draws <= population:
        raise ValueError("need 0 <= successes, draws <= population")
    return Fraction(
        n_choose_k(successes, k) * n_choose_k(population - successes, draws - k),
        n_choose_k(population, draws),
    )


def hypergeometric_cdf(k: int, population: int, successes: int, draws: int) -> Fraction:
    """P(X <= k) for the hypergeometric distribution."""
    return sum(
        (hypergeometric_pmf(i, population, successes, draws) for i in range(0, k + 1)),
        Fraction(0),
    )


def hypergeometric_mean(population: int, successes: int, draws: int) -> Fraction:
    return Fraction(draws * successes, population)


def hypergeometric_variance(population: int, successes: int, draws: int) -> Fraction:
    """n·(K/N)·(1 − K/N)·(N − n)/(N − 1): binomial variance times the finite-population term."""
    if population <= 1:
        return Fraction(0)
    p = Fraction(successes, population)
    return draws * p * (1 - p) * Fraction(population - draws, population - 1)


@dataclass(frozen=True)
class MCResult:
    """Monte Carlo estimate of E[X]."""

    n: int
    mean: float
    variance: float  # sample variance of X (n − 1 denominator)

    @property
    def std_err(self) -> float:
        """Standard error of the mean: s / sqrt(n)."""
        return math.sqrt(self.variance / self.n) if self.n > 0 else math.inf

    def ci(self, z: float = 1.96) -> tuple[float, float]:
        """Normal-approximation confidence interval (z = 1.96 gives about 95%)."""
        half = z * self.std_err
        return (self.mean - half, self.mean + half)


def monte_carlo(trial: Callable[[Rng], float], n: int, rng: Rng) -> MCResult:
    """Run `trial` n times and return the mean with its standard error.

    Uses Welford's online update, which avoids the cancellation error of
    computing sum(x²) − n·mean².
    """
    if n < 2:
        raise ValueError("need at least 2 trials for a standard error")
    mean = 0.0
    m2 = 0.0
    for i in range(1, n + 1):
        x = float(trial(rng))
        delta = x - mean
        mean += delta / i
        m2 += delta * (x - mean)
    return MCResult(n=n, mean=mean, variance=m2 / (n - 1))
