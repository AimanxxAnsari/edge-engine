"""`edge-engine lab market`: exact contract statistics and the economics of quote width."""

from __future__ import annotations

import math
from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from ...prob import MCResult
from ...rng import Rng
from . import bots, contract

HALF_WIDTHS = (0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 1.0)  # in standard deviations
SHARES = (0.0, 0.2, 0.4)


def play_symmetric(
    rng: Rng, kind: str, n: int, half: float, share: float, n_bots: int, limit: int
) -> bots.Breakdown:
    """One game quoting fair ± half·sd every round (no skew)."""
    if kind == "dice":
        items = [rng.randint(1, 6) for _ in range(n)]
    else:
        items = rng.sample([v for v in contract.CARD_VALUES for _ in range(4)], n)
    trades: list[bots.Trade] = []
    position = 0
    for r in range(n):
        revealed = items[:r]
        fair = contract.fair_value(kind, revealed, n)
        h = bots.price(half * contract.std_dev(kind, revealed, n))
        new = bots.run_round(
            rng, kind, items, r, fair - h, fair + h, position, n_bots, share, limit, r
        )
        position += sum(t.side for t in new)
        trades += new
    return bots.breakdown(trades, Fraction(sum(items)))


def summarise(values: list[float]) -> MCResult:
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return MCResult(n=n, mean=mean, variance=var)


def run(config: Mapping[str, Any], rng: Rng) -> str:
    kind = str(config.get("contract", "dice"))
    n = int(config.get("n", 4))
    games = int(config.get("games", 400))
    n_bots = int(config.get("bots", 4))
    limit = int(config.get("limit", 5))
    if kind not in contract.KINDS or not 1 <= n <= 10 or games < 2:
        raise ValueError("need contract dice or cards, 1 <= n <= 10 and games >= 2")

    out = ["Exact statistics of the sum (nothing revealed yet):", ""]
    out.append(
        f"{'n':>3} {'dice mean':>10} {'var':>7} {'sd':>6}   "
        f"{'cards mean':>10} {'var':>7} {'sd':>6} {'(with repl.)':>12}"
    )
    for k in range(1, 6):
        dm, dv = contract.fair_value("dice", [], k), contract.variance("dice", [], k)
        cm, cv = contract.fair_value("cards", [], k), contract.variance("cards", [], k)
        with_repl = k * Fraction(14)
        out.append(
            f"{k:3d} {float(dm):10.1f} {float(dv):7.3f} {math.sqrt(dv):6.3f}   "
            f"{float(cm):10.1f} {float(cv):7.3f} {math.sqrt(cv):6.3f} {float(with_repl):12.3f}"
        )
    out += [
        "Cards: variance k·14·(52 − k)/51 without replacement, k·14 with it.",
        "",
        f"Quoting fair ± half-width every round on the sum of {n} {kind}, {n_bots} bots a "
        f"round, {games} games each. Mean P&L per game (± SE), split into spread "
        "income and adverse selection (luck averages out):",
        "",
        f"{'informed':>8} {'half-width':>10} {'P&L':>14} {'spread':>8} {'adverse':>8}",
    ]
    for share in SHARES:
        best = None
        for half in HALF_WIDTHS:
            results = [
                play_symmetric(rng, kind, n, half, share, n_bots, limit) for _ in range(games)
            ]
            total = summarise([float(b.total) for b in results])
            spread = sum(float(b.spread) for b in results) / games
            adverse = sum(float(b.adverse) for b in results) / games
            edge = spread + adverse  # expected P&L, without the luck term
            if best is None or edge > best[1]:
                best = (half, edge)
            out.append(
                f"{share:8.0%} {half:8.2f}sd {total.mean:+8.2f} ± {total.std_err:4.2f} "
                f"{spread:+8.2f} {adverse:+8.2f}"
            )
        out.append(f"{'':8} best half-width ≈ {best[0]:.2f} sd (spread + adverse {best[1]:+.2f})")
        out.append("")
    out.append("With no informed traders the best half-width is sd/2 (a market one sd wide):")
    out.append("noise traders value the contract at fair ± sd, so at half-width h each side")
    out.append("trades with chance (sd − h)/(2·sd) and earns h, which is largest at h = sd/2.")
    out.append("Informed traders trade exactly when you are wrong, so they push the best")
    out.append("width out (about 0.5 sd → 0.6 sd here) and make tight markets lose money.")
    return "\n".join(out)
