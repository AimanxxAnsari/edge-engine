"""Kelly-criterion maths: growth rates, exact final-wealth distribution, Bayes updating."""

from __future__ import annotations

import math

from ...prob import binomial_pmf
from ...rng import Rng


def kelly_fraction(p: float, b: float = 1.0) -> float:
    """f* = (b·p − q) / b for net odds b. Negative means bet the other side."""
    if not 0.0 <= p <= 1.0 or b <= 0:
        raise ValueError("need 0 <= p <= 1 and b > 0")
    return (b * p - (1.0 - p)) / b


def growth_rate(f: float, p: float, b: float = 1.0) -> float:
    """Expected log growth per bet: g(f) = p·ln(1 + b·f) + q·ln(1 − f).

    For an even-money bet (b = 1) a negative f is a bet on the other side.
    Returns -inf when a single loss can wipe you out.
    """
    q = 1.0 - p
    win, lose = 1.0 + b * f, 1.0 - f
    if win <= 0 and p > 0 or lose <= 0 and q > 0:
        return -math.inf
    total = 0.0
    if p > 0:
        total += p * math.log(win)
    if q > 0:
        total += q * math.log(lose)
    return total


def zero_growth_fraction(p: float, b: float = 1.0) -> float:
    """The fraction above Kelly where growth falls back to zero (bisection)."""
    f_star = kelly_fraction(p, b)
    if f_star <= 0:
        return 0.0
    lo, hi = f_star, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if growth_rate(mid, p, b) > 0:
            lo = mid
        else:
            hi = mid
    return lo


def final_wealth(w0: float, f: float, wins: int, n: int, b: float = 1.0) -> float:
    """Wealth after n bets at fraction f with this many wins (order doesn't matter)."""
    return w0 * (1.0 + b * f) ** wins * (1.0 - f) ** (n - wins)


def mean_final_wealth(w0: float, f: float, p: float, n: int, b: float = 1.0) -> float:
    """E[W_n] = W0·(1 + f·(b·p − q))^n."""
    return w0 * (1.0 + f * (b * p - (1.0 - p))) ** n


def median_final_wealth(w0: float, f: float, p: float, n: int, b: float = 1.0) -> float:
    """Wealth rises with the number of wins, so the median is the wealth at the median k."""
    if not 0 <= f < 1:
        raise ValueError("need 0 <= f < 1")
    cdf = 0.0
    for k in range(n + 1):
        cdf += binomial_pmf(k, n, p)
        if cdf >= 0.5:
            return final_wealth(w0, f, k, n, b)
    return final_wealth(w0, f, n, n, b)


def prob_below(x: float, f: float, p: float, n: int, b: float = 1.0) -> float:
    """P(W_n < x·W0) when betting fraction f on the favoured side every time."""
    if not 0 <= f < 1:
        raise ValueError("need 0 <= f < 1")
    return sum(binomial_pmf(k, n, p) for k in range(n + 1) if final_wealth(1.0, f, k, n, b) < x)


def drawdown_approx(x: float, c: float) -> float:
    """Continuous approximation: P(ever falling to x·W0) betting c × Kelly ≈ x^(2/c − 1)."""
    if not 0 < x < 1 or c <= 0:
        raise ValueError("need 0 < x < 1 and c > 0")
    exponent = 2.0 / c - 1.0
    return 1.0 if exponent <= 0 else x**exponent


def gamblers_ruin(units: float, p: float) -> float:
    """P(ever going broke) with fixed bets, `units` bets of bankroll, no time limit."""
    q = 1.0 - p
    if p <= q:
        return 1.0
    return (q / p) ** units


# --- unknown bias: Beta prior ----------------------------------------------


def posterior_mean(a: float, b: float, heads: int, tails: int) -> float:
    """Mean of Beta(a + heads, b + tails)."""
    return (a + heads) / (a + b + heads + tails)


def sample_beta(rng: Rng, a: int, b: int) -> float:
    """Beta(a, b) for whole a, b: the a-th smallest of a + b − 1 uniforms."""
    if a < 1 or b < 1 or int(a) != a or int(b) != b:
        raise ValueError("a and b must be whole numbers >= 1")
    u = sorted(rng.random() for _ in range(int(a) + int(b) - 1))
    return u[int(a) - 1]
