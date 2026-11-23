"""`edge-engine lab blackjack`: chart, edge, dealer bust chances and deviation indices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...rng import Rng
from . import count as hilo
from .ev import (
    INFINITE,
    Situation,
    Solver,
    comp_at_true_count,
    dealer_outcomes,
    normalise,
)
from .module import parse_rules
from .strategy import UP_LABEL, UPCARDS, hard_combos, render, table

INDEX_DECKS_LEFT = 3.0  # shoe depth used when computing indices


def shoe_at_true_count(tc: float, decks_left: float, removed: tuple[int, ...]) -> tuple:
    """Average shoe of `decks_left` decks at a true count, with known cards removed."""
    low, high = (20 - tc / 2) / 5, (20 + tc / 2) / 20
    counts = [4 * high * decks_left] + [low * decks_left] * 5 + [4.0 * decks_left] * 3
    counts += [16 * high * decks_left]
    for v in removed:
        counts[v - 1] -= 1
    return normalise(counts)


def deviation_margin(d: hilo.Deviation, tc: float, rules) -> float:
    """EV(deviation play) − EV(the other play), averaged over two-card hands."""
    kind, rest = d.hand.split()
    if kind == "pair":
        v = 10 if rest == "TT" else 1 if rest == "AA" else int(rest[0])
        combos = [(v, v)]
    else:
        combos = hard_combos(int(rest))
    margin = 0.0
    for c1, c2 in combos:
        comp = shoe_at_true_count(tc, INDEX_DECKS_LEFT, (c1, c2, d.up))
        evs = Solver(comp, rules).evs(Situation(c1 + c2, False, d.up, c1 if c1 == c2 else None))
        if d.at_or_above == "surrender":
            margin += -0.5 - max(evs["hit"], evs["stand"])
        else:
            margin += evs[d.at_or_above] - evs[d.below]
    return margin / len(combos)


def computed_index(d: hilo.Deviation, rules) -> float | None:
    """Lowest true count (0.1 steps, −12 to +12) where the deviation play is better."""
    for step in range(-120, 121):
        tc = step / 10
        if deviation_margin(d, tc, rules) > 0:
            return tc
    return None


def computed_insurance_index() -> float:
    for step in range(-100, 121):
        tc = step / 10
        if shoe_at_true_count(tc, INDEX_DECKS_LEFT, (1,))[9] > 1 / 3:
            return tc
    raise RuntimeError("no insurance index found")


def run(config: Mapping[str, Any], rng: Rng) -> str:
    rules = parse_rules(config)
    out = [f"Rules: {rules.describe()}.", ""]
    out.append(f"Basic strategy ({rules.decks} decks, known cards removed):")
    out.append(render(table(rules, decks=rules.decks)))
    out.append("H hit, S stand, D double (else hit), Ds double (else stand), P split,")
    out.append("Rh/Rs/Rp surrender (else hit/stand/split).")
    out.append("")
    edge = Solver(INFINITE, rules).round_ev()
    out.append(f"Player's edge with perfect basic strategy (infinite deck): {edge:+.3%}.")
    out.append("Edge by true count (average shoe at that count):")
    row = []
    for tc in range(-2, 7):
        row.append(f"{tc:+d}: {Solver(comp_at_true_count(tc), rules).round_ev():+.2%}")
    out.append("  " + "  ".join(row))
    out.append("")
    out.append("Dealer final totals by upcard (infinite deck, after peeking):")
    out.append(f"{'up':>4} " + " ".join(f"{t:>6}" for t in ("17", "18", "19", "20", "21", "bust")))
    for up in UPCARDS:
        d = dealer_outcomes(up, INFINITE, rules.h17)
        out.append(
            f"{UP_LABEL[up]:>4} " + " ".join(f"{d[t]:6.1%}" for t in (17, 18, 19, 20, 21, 22))
        )
    out.append("")
    if rules.h17:
        out.append("Deviation indices are published for S17; showing S17 values.")
    s17 = parse_rules({**config, "h17": False})
    no_surrender = parse_rules({**config, "h17": False, "surrender": False})
    out.append(
        f"Count plays: computed index (average shoe, {INDEX_DECKS_LEFT:g} decks left) "
        "against the published one (Schlesinger)."
    )
    out.append(
        f"  {'insurance':22} take at TC >= {computed_insurance_index():+5.1f}   "
        f"published {hilo.INSURANCE_INDEX:+d}"
    )
    for d in hilo.DEVIATIONS:
        r = s17 if d.group == "Fab4" else no_surrender
        idx = computed_index(d, r)
        shown = "  none" if idx is None else f"{idx:+5.1f}"
        out.append(f"  {d.name:22} {d.at_or_above} at TC >= {shown}   published {d.index:+d}")
    return "\n".join(out)
