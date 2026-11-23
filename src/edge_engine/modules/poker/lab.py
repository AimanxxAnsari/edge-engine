"""`edge-engine lab poker`: CFR convergence, Kuhn strategy against theory, evaluator, equity."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from ...rng import Rng
from . import equity as eq
from .cfr import CFRPlus, Tree
from .evaluator import CATEGORIES, cards, category, evaluate
from .games import Kuhn, Leduc

SEVEN_CARD_COUNTS = (  # out of C(52, 7) = 133,784,560
    23_294_460,
    58_627_800,
    31_433_400,
    6_461_620,
    6_180_020,
    4_047_644,
    3_473_184,
    224_848,
    41_584,
)
SEVEN_CARD_TOTAL = 133_784_560


def convergence(game, checkpoints) -> list[str]:
    tree = Tree(game)
    solver = CFRPlus(tree)
    lines = [f"{game.name}: {len(tree.infosets)} information sets, {len(tree.deals)} deals"]
    done = 0
    for n in checkpoints:
        solver.iterate(n - done)
        done = n
        avg = solver.average()
        lines.append(
            f"  {n:6d} iterations: value {tree.value(avg):+.5f}, "
            f"exploitability {tree.exploitability(avg):.6f}"
        )
    return lines


def kuhn_strategy(iterations: int = 2000) -> dict[str, float]:
    """Probability of 'b' (bet or call) at each Kuhn information set."""
    tree = Tree(Kuhn())
    avg = CFRPlus(tree).solve(iterations)
    return {key: float(avg[i, 1]) for i, key in enumerate(tree.infosets)}


def run(config: Mapping[str, Any], rng: Rng) -> str:
    samples = int(config.get("samples", 20000))
    out = ["CFR+ convergence (exploitability 0 = Nash equilibrium):"]
    out += convergence(Kuhn(), (10, 100, 1000, 3000))
    out.append("  Kuhn's game value is −1/18 = −0.05556 for the first player.")
    out += convergence(Leduc(), (10, 100, 500, 1500))
    out.append("  Published game value of Leduc Hold'em for the first player: about −0.0856.")
    out.append("")

    s = kuhn_strategy()
    alpha = s["J:"]
    out.append("Kuhn equilibrium found (probability of betting or calling):")
    out.append(
        f"  first player:  bet J {alpha:.3f} (= α), bet K {s['K:']:.3f} (theory 3α = "
        f"{3 * alpha:.3f}), bet Q {s['Q:']:.3f} (theory 0)"
    )
    out.append(
        f"                 after check-bet: call Q {s['Q:pb']:.3f} (theory α + 1/3 = "
        f"{alpha + 1 / 3:.3f}), call J {s['J:pb']:.3f}, call K {s['K:pb']:.3f}"
    )
    out.append(
        f"  second player: bluff J after a check {s['J:p']:.3f} (theory 1/3), "
        f"call Q {s['Q:b']:.3f} (1/3), bet K {s['K:p']:.3f} (1), call J {s['J:b']:.3f} (0)"
    )
    out.append("")

    counts: Counter[int] = Counter()
    for _ in range(samples):
        counts[category(evaluate(rng.sample(range(52), 7)))] += 1
    out.append(f"Seven-card hands: {samples:,} random hands against the exact frequencies")
    for c in range(8, -1, -1):
        exact = SEVEN_CARD_COUNTS[c] / SEVEN_CARD_TOTAL
        seen = counts[c] / samples
        se = (exact * (1 - exact) / samples) ** 0.5
        out.append(
            f"  {CATEGORIES[c]:16} {seen:8.4%}  exact {exact:8.4%}  ({(seen - exact) / se:+.1f} SE)"
            if se
            else f"  {CATEGORIES[c]:16} {seen:8.4%}"
        )
    out.append("")

    out.append("Equity (exact from the flop, Monte Carlo preflop):")
    spots = [
        ("Ah Kh", "Qs Qd", "2h 7h Jc"),
        ("8s 9s", "Ac Ad", "6s 7d 2s"),
        ("Jc Td", "As Kc", "Qh 9h 3c"),
    ]
    for hero, villain, board in spots:
        e = eq.exact(cards(hero), cards(villain), cards(board))
        out.append(f"  {hero} vs {villain} on {board}: {float(e.equity):.1%} ({e.boards} boards)")
    for hero, villain in (("As Ah", "Ks Kh"), ("As Kd", "Qc Qh"), ("7c 2d", "Ad Kc")):
        r = eq.monte_carlo_equity(rng, cards(hero), cards(villain), [], 4000)
        out.append(f"  {hero} vs {villain} preflop: {r.mean:.1%} ± {r.std_err:.1%}")
    return "\n".join(out)
