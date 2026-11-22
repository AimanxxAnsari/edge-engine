"""`edge-engine lab kelly`: exact values and simulations for a range of bet fractions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...rng import Rng
from . import kmath, sim


def run(config: Mapping[str, Any], rng: Rng) -> str:
    p = float(config.get("p", 0.6))
    n = int(config.get("flips", 300))
    runs = int(config.get("runs", 1000))
    w0 = float(config.get("start", 25))
    if not 0.5 < p < 1:
        raise ValueError("p must be between 0.5 and 1 for the lab")
    if n < 1 or runs < 2:
        raise ValueError("need flips >= 1 and runs >= 2")
    f_star = kmath.kelly_fraction(p)
    fractions = sorted({round(f_star * c, 4) for c in (0.25, 0.5, 1, 1.5, 2, 2.5)} - {0})
    fractions = [f for f in fractions if f < 1]

    out = [
        f"Coin: p = {p}, even money. Start ${w0:,.2f}, {n} flips, {runs:,} simulated runs.",
        f"Kelly fraction f* = 2p − 1 = {f_star:.4f}. Growth falls back to zero at "
        f"f = {kmath.zero_growth_fraction(p):.4f}.",
        "",
        f"{'f':>6} {'×Kelly':>6} {'g(f)':>9} {'mean':>12} {'median':>11} "
        f"{'P(<start)':>9} {'P(halve) sim':>15} {'approx':>7}",
    ]
    for f in fractions:
        c = f / f_star
        paths = sim.simulate_paths(rng, w0, f, p, n, runs)
        dd = sim.drawdown_frequency(paths, 0.5)
        out.append(
            f"{f:6.3f} {c:6.2f} {kmath.growth_rate(f, p):9.5f} "
            f"{sim.short_money(kmath.mean_final_wealth(w0, f, p, n)):>12} "
            f"{sim.short_money(kmath.median_final_wealth(w0, f, p, n)):>11} "
            f"{kmath.prob_below(1.0, f, p, n):9.3f} "
            f"{dd.value:8.3f} ± {dd.std_err:.3f} {kmath.drawdown_approx(0.5, c):7.3f}"
        )
    out += [
        "",
        "mean and median are exact; P(<start) is exact (binomial).",
        "P(halve) = chance of ever falling to half the start; approx = 0.5^(2/c − 1).",
        "The mean is pulled up by rare huge runs; the median is what a typical player gets.",
        "",
        f"Fan chart: Kelly (f = {f_star:.3f}), {runs:,} runs",
        sim.fan_chart(sim.simulate_paths(rng, w0, f_star, p, n, runs)),
        "",
        "Fixed-size bets instead (go broke when you can't cover the next bet):",
    ]
    for bet in (1, 5, 10):
        units = int(w0 // bet)  # losses in a row (net) that leave you unable to bet
        ruin = sim.fixed_bet_ruin(rng, int(w0 * 100), bet * 100, p, n, runs)
        out.append(
            f"  ${bet:>2} a flip: no time limit {kmath.gamblers_ruin(units, p):.3f} "
            f"(exact (q/p)^{units}); within {n} flips {ruin.value:.3f} ± {ruin.std_err:.3f}"
        )
    return "\n".join(out)
