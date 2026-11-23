"""Basic-strategy tables in the usual chart notation.

Codes: H hit, S stand, D double (else hit), Ds double (else stand), P split,
Rh / Rs / Rp surrender (else hit / stand / split).
"""

from __future__ import annotations

from .cards import Rules
from .ev import INFINITE, Comp, Situation, Solver, comp_without, full_shoe

UPCARDS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 1)
UP_LABEL = {1: "A", 10: "T", **{n: str(n) for n in range(2, 10)}}
HARD_ROWS = tuple(range(5, 21))
SOFT_ROWS = tuple(range(2, 10))  # A2 .. A9 (the non-ace card)
PAIR_ROWS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 1)


def code(evs: dict[str, float]) -> str:
    """Chart code for the best action, with its fallback when the best isn't allowed."""
    order = sorted(evs, key=lambda a: -evs[a])
    best = order[0]
    rest = [a for a in order if a not in ("double", "surrender")]
    if best == "double":
        return "Ds" if evs["stand"] > evs["hit"] else "D"
    if best == "surrender":
        nxt = rest[0]
        return {"hit": "Rh", "stand": "Rs", "split": "Rp"}[nxt]
    return {"hit": "H", "stand": "S", "split": "P"}[best]


def hard_situation(total: int, up: int) -> Situation:
    """A two-card hard total that is not a pair (e.g. 16 = 10 + 6)."""
    return Situation(hard=total, ace=False, up=up)


def soft_situation(other: int, up: int) -> Situation:
    return Situation(hard=1 + other, ace=True, up=up)


def pair_situation(value: int, up: int) -> Situation:
    return Situation(hard=2 * value, ace=value == 1, up=up, pair=value)


def hard_combos(t: int) -> list[tuple[int, int]]:
    """Two-card hands (no ace, no pair) that make hard total t."""
    return [(a, t - a) for a in range(2, 10) if a < t - a <= 10]


def _weighted_evs(rules: Rules, decks: int, combos, up: int, make) -> dict[str, float]:
    """EVs averaged over the two-card hands that make a total, each with its cards removed."""
    base = full_shoe(decks)
    if not combos:  # e.g. hard 20 is never two different cards: remove only the upcard
        return Solver(comp_without(decks, [up]), rules).evs(make(0, 0))
    total_w = 0.0
    acc: dict[str, float] = {}
    for c1, c2 in combos:
        w = base[c1 - 1] * (base[c2 - 1] - (c1 == c2)) * (1 if c1 == c2 else 2)
        solver = Solver(comp_without(decks, [c1, c2, up]), rules)
        for action, ev in solver.evs(make(c1, c2)).items():
            acc[action] = acc.get(action, 0.0) + w * ev
        total_w += w
    return {a: v / total_w for a, v in acc.items()}


def table(
    rules: Rules, comp: Comp = INFINITE, decks: int | None = None
) -> dict[str, dict[int, str]]:
    """Rows keyed 'hard 16', 'soft A7', 'pair 88'; columns keyed by upcard value.

    With `decks`, each hand is evaluated on a shoe of that size with the player's two
    cards and the dealer's upcard removed, averaged over the two-card hands that make
    the total. Otherwise every hand uses the fixed composition `comp`.
    """
    out: dict[str, dict[int, str]] = {}
    if decks is None:
        solver = Solver(comp, rules)
        for t in HARD_ROWS:
            out[f"hard {t}"] = {up: code(solver.evs(hard_situation(t, up))) for up in UPCARDS}
        for o in SOFT_ROWS:
            out[f"soft A{o}"] = {up: code(solver.evs(soft_situation(o, up))) for up in UPCARDS}
        for v in PAIR_ROWS:
            name = UP_LABEL[v] * 2
            out[f"pair {name}"] = {up: code(solver.evs(pair_situation(v, up))) for up in UPCARDS}
        return out
    for t in HARD_ROWS:
        out[f"hard {t}"] = {
            up: code(
                _weighted_evs(
                    rules,
                    decks,
                    hard_combos(t),
                    up,
                    lambda a, b, up=up, t=t: Situation(t, False, up),
                )
            )
            for up in UPCARDS
        }
    for o in SOFT_ROWS:
        out[f"soft A{o}"] = {
            up: code(
                _weighted_evs(rules, decks, [(1, o)], up, lambda a, b, up=up: soft_situation(b, up))
            )
            for up in UPCARDS
        }
    for v in PAIR_ROWS:
        name = UP_LABEL[v] * 2
        out[f"pair {name}"] = {
            up: code(
                _weighted_evs(rules, decks, [(v, v)], up, lambda a, b, up=up: pair_situation(a, up))
            )
            for up in UPCARDS
        }
    return out


def render(tab: dict[str, dict[int, str]]) -> str:
    head = f"{'':10}" + "".join(f"{UP_LABEL[u]:>4}" for u in UPCARDS)
    lines = [head]
    for name, row in tab.items():
        if name in ("soft A2", "pair 22"):
            lines.append("")
        lines.append(f"{name:10}" + "".join(f"{row[u]:>4}" for u in UPCARDS))
    return "\n".join(lines)
