"""Equity of one hand against another: exact enumeration and Monte Carlo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from ...prob import MCResult, monte_carlo
from ...rng import Rng
from .evaluator import evaluate

DECK = tuple(range(52))


@dataclass(frozen=True)
class Equity:
    win: Fraction
    tie: Fraction
    lose: Fraction
    boards: int

    @property
    def equity(self) -> Fraction:
        """Share of the pot: wins plus half of ties."""
        return self.win + self.tie / 2


def _check(hero: Sequence[int], villain: Sequence[int], board: Sequence[int]) -> list[int]:
    used = list(hero) + list(villain) + list(board)
    if len(set(used)) != len(used):
        raise ValueError("a card is used twice")
    if len(hero) != 2 or len(villain) != 2 or len(board) > 5:
        raise ValueError("need two hole cards each and at most five board cards")
    return [c for c in DECK if c not in used]


def exact(hero: Sequence[int], villain: Sequence[int], board: Sequence[int]) -> Equity:
    """Enumerate every way the board can finish."""
    rest = _check(hero, villain, board)
    need = 5 - len(board)
    win = tie = total = 0
    for extra in combinations(rest, need):
        full = list(board) + list(extra)
        a = evaluate(list(hero) + full)
        b = evaluate(list(villain) + full)
        total += 1
        if a > b:
            win += 1
        elif a == b:
            tie += 1
    return Equity(
        Fraction(win, total), Fraction(tie, total), Fraction(total - win - tie, total), total
    )


def monte_carlo_equity(
    rng: Rng,
    hero: Sequence[int],
    villain: Sequence[int] | None,
    board: Sequence[int],
    n: int,
) -> MCResult:
    """Equity by simulation; `villain=None` means a random hand."""
    fixed = list(hero) + list(villain or []) + list(board)
    if len(set(fixed)) != len(fixed):
        raise ValueError("a card is used twice")
    rest = [c for c in DECK if c not in fixed]
    need = 5 - len(board) + (0 if villain else 2)

    def trial(r: Rng) -> float:
        drawn = r.sample(rest, need)
        opp = list(villain) if villain else drawn[:2]
        full = list(board) + (drawn if villain else drawn[2:])
        a = evaluate(list(hero) + full)
        b = evaluate(opp + full)
        return 1.0 if a > b else 0.5 if a == b else 0.0

    return monte_carlo(trial, n, rng)


def outs(hero: Sequence[int], villain: Sequence[int], board: Sequence[int]) -> list[int]:
    """Unseen cards that put hero strictly ahead on the next street (from behind or tied)."""
    rest = _check(hero, villain, board)
    if not 3 <= len(board) <= 4:
        raise ValueError("outs need a flop or turn")
    result = []
    for c in rest:
        full = list(board) + [c]
        if evaluate(list(hero) + full) > evaluate(list(villain) + full):
            result.append(c)
    return result


def two_card_chance(n_outs: int, unseen: int) -> float:
    """Chance of hitting at least one of n outs in the next two cards."""
    return 1 - (unseen - n_outs) / unseen * (unseen - 1 - n_outs) / (unseen - 1)
