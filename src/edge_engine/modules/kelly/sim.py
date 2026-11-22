"""Simulation of betting strategies and a text fan chart."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ...rng import Rng


def simulate_paths(
    rng: Rng, w0: float, f: float, p: float, n: int, runs: int, b: float = 1.0
) -> list[list[float]]:
    """`runs` wealth paths of n bets at fraction f (each path has n + 1 points)."""
    paths = []
    for _ in range(runs):
        w = w0
        path = [w]
        for _ in range(n):
            stake = f * w
            w = w + b * stake if rng.random() < p else w - stake
            path.append(w)
        paths.append(path)
    return paths


def quantile(sorted_xs: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile of already sorted data."""
    if not sorted_xs:
        raise ValueError("no data")
    pos = q * (len(sorted_xs) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


@dataclass(frozen=True)
class Proportion:
    """A simulated probability with its standard error."""

    value: float
    std_err: float
    runs: int


def proportion(hits: int, runs: int) -> Proportion:
    p = hits / runs
    return Proportion(p, math.sqrt(p * (1 - p) / runs), runs)


def drawdown_frequency(paths: list[list[float]], x: float) -> Proportion:
    """Share of paths that ever fell to x × the starting wealth."""
    hits = sum(1 for path in paths if min(path) <= x * path[0])
    return proportion(hits, len(paths))


def fixed_bet_ruin(rng: Rng, w0: int, bet: int, p: float, n: int, runs: int) -> Proportion:
    """Share of runs that go broke betting a fixed amount (even money) within n bets."""
    hits = 0
    for _ in range(runs):
        w = w0
        for _ in range(n):
            w += bet if rng.random() < p else -bet
            if w < bet:  # can't cover the next bet
                hits += 1
                break
    return proportion(hits, runs)


def short_money(x: float) -> str:
    """$12.34, $10,504, $3.22M, $266B."""
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(x) >= size:
            return f"${x / size:.3g}{suffix}"
    return f"${x:,.0f}" if abs(x) >= 1000 else f"${x:,.2f}"


BANDS = (0.05, 0.25, 0.5, 0.75, 0.95)


def fan_chart(paths: list[list[float]], width: int = 60, height: int = 14) -> str:
    """Percentile bands of wealth over time, on a log scale.

    '*' median, '#' middle 50%, '.' middle 90%, '-' the starting wealth.
    """
    n = len(paths[0]) - 1
    w0 = paths[0][0]
    cols = min(width, n + 1)
    times = [round(i * n / (cols - 1)) for i in range(cols)] if cols > 1 else [0]
    floor = 1e-9  # log of zero wealth
    bands = []
    for t in times:
        xs = sorted(max(path[t], floor) for path in paths)
        bands.append([math.log10(quantile(xs, q)) for q in BANDS])
    top = max(b[-1] for b in bands)
    bottom = min(b[0] for b in bands)
    start = math.log10(w0)
    top, bottom = max(top, start), min(bottom, start)
    if top - bottom < 1e-9:
        top, bottom = top + 0.5, bottom - 0.5
    step = (top - bottom) / (height - 1)

    def row_of(v: float) -> int:
        return round((top - v) / step)

    grid = [[" "] * cols for _ in range(height)]
    start_row = row_of(start)
    for c, (p5, p25, p50, p75, p95) in enumerate(bands):
        for r in range(row_of(p95), row_of(p5) + 1):
            grid[r][c] = "."
        for r in range(row_of(p75), row_of(p25) + 1):
            grid[r][c] = "#"
        grid[row_of(p50)][c] = "*"
        if grid[start_row][c] == " ":
            grid[start_row][c] = "-"

    labels = {0: short_money(10**top), height - 1: short_money(10**bottom)}
    labels[start_row] = f"start {short_money(w0)}"
    lines = [f"{labels.get(r, ''):>14} |{''.join(row)}" for r, row in enumerate(grid)]
    lines.append(f"{'':>14} +{'-' * cols}")
    end = f"bet {n}"
    axis = "0" + end.rjust(cols - 1) if cols > len(end) + 2 else f"0 to {end}"
    lines.append(f"{'':>14}  {axis}")
    lines.append(f"{'':>14}  * median   # middle 50%   . middle 90%   - start")
    return "\n".join(lines)
