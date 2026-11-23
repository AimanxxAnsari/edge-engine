"""Exact statistics for "sum of n items" contracts: dice, or cards without replacement.

Everything is a Fraction. Cards are valued A = 1 ... K = 13, four of each in one deck.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from fractions import Fraction

from ...prob import n_choose_k

DIE = range(1, 7)
CARD_VALUES = range(1, 14)
KINDS = ("dice", "cards")


def unseen_cards(revealed: Sequence[int]) -> dict[int, int]:
    """Card counts by value after removing the revealed cards from one deck."""
    counts = {v: 4 for v in CARD_VALUES}
    for v in revealed:
        if counts.get(v, 0) <= 0:
            raise ValueError(f"too many cards of value {v}")
        counts[v] -= 1
    return counts


def pool_stats(counts: dict[int, int]) -> tuple[int, Fraction, Fraction]:
    """(R, mean, population variance) of a multiset of card values."""
    r = sum(counts.values())
    if r == 0:
        raise ValueError("no cards left")
    mean = Fraction(sum(v * c for v, c in counts.items()), r)
    var = Fraction(sum(c * (v - mean) ** 2 for v, c in counts.items()), r)
    return r, mean, var


def fair_value(kind: str, revealed: Sequence[int], n: int) -> Fraction:
    """E[sum of all n items | the revealed ones]."""
    m = n - len(revealed)
    if m < 0:
        raise ValueError("more revealed than items")
    known = Fraction(sum(revealed))
    if kind == "dice":
        return known + Fraction(7, 2) * m
    if m == 0:
        return known
    _, mean, _ = pool_stats(unseen_cards(revealed))
    return known + m * mean


def variance(kind: str, revealed: Sequence[int], n: int) -> Fraction:
    """Var[sum | revealed]. Cards use the finite-population correction (R − m)/(R − 1)."""
    m = n - len(revealed)
    if kind == "dice":
        return Fraction(35, 12) * m
    if m == 0:
        return Fraction(0)
    r, _, var = pool_stats(unseen_cards(revealed))
    if r == 1:
        return Fraction(0)
    return m * var * Fraction(r - m, r - 1)


def std_dev(kind: str, revealed: Sequence[int], n: int) -> float:
    return math.sqrt(variance(kind, revealed, n))


def informed_value(kind: str, revealed: Sequence[int], peek: int, n: int) -> Fraction:
    """What a trader who has seen the next item (`peek`) thinks the sum is worth."""
    return fair_value(kind, list(revealed) + [peek], n)


def distribution(kind: str, revealed: Sequence[int], n: int) -> dict[int, Fraction]:
    """Exact distribution of the final sum given the revealed items."""
    m = n - len(revealed)
    known = sum(revealed)
    if kind == "dice":
        dist = {0: Fraction(1)}
        for _ in range(m):
            nxt: dict[int, Fraction] = {}
            for s, p in dist.items():
                for face in DIE:
                    nxt[s + face] = nxt.get(s + face, Fraction(0)) + p / 6
            dist = nxt
        return {known + s: p for s, p in dist.items()}
    counts = unseen_cards(revealed)
    # ways[k][s]: ways to choose k physical cards with value sum s
    ways: list[dict[int, int]] = [dict() for _ in range(m + 1)]
    ways[0][0] = 1
    for v, c in counts.items():
        new = [dict(w) for w in ways]
        for k in range(m + 1):
            for s, w in ways[k].items():
                for j in range(1, min(c, m - k) + 1):
                    key = s + j * v
                    new[k + j][key] = new[k + j].get(key, 0) + w * n_choose_k(c, j)
        ways = new
    total = n_choose_k(sum(counts.values()), m)
    return {known + s: Fraction(w, total) for s, w in ways[m].items()}


def prob_at_least(kind: str, revealed: Sequence[int], n: int, x: int) -> Fraction:
    return sum((p for s, p in distribution(kind, revealed, n).items() if s >= x), Fraction(0))


def item_label(kind: str, value: int) -> str:
    if kind == "dice":
        return str(value)
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(value, str(value))
