"""Hi-Lo counting, bet spread and the published count-based strategy changes."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .cards import HILO


def running_count(cards: Iterable[str]) -> int:
    return sum(HILO[c] for c in cards)


def true_count(rc: float, cards_left: int) -> float:
    """Running count per deck of unseen cards."""
    if cards_left <= 0:
        raise ValueError("no cards left")
    return rc / (cards_left / 52)


SPREAD = ((5, 8), (4, 6), (3, 4), (2, 2))  # (floor TC at least, units)


def bet_units(tc: float) -> int:
    """1-8 spread on the floor of the true count: ≤1 → 1, 2 → 2, 3 → 4, 4 → 6, 5+ → 8."""
    t = math.floor(tc)
    for at_least, units in SPREAD:
        if t >= at_least:
            return units
    return 1


@dataclass(frozen=True)
class Deviation:
    """Play `at_or_above` when the true count is at least `index`, else `below`."""

    name: str
    hand: str  # 'hard 16', 'pair TT'
    up: int  # dealer upcard value (1 = ace)
    at_or_above: str
    below: str
    index: int
    group: str  # 'I18' or 'Fab4'


# Schlesinger, Blackjack Attack: Illustrious 18 and Fab 4 for multi-deck, S17, DAS.
# The I18 hit/stand/double/split indices assume no surrender; the Fab 4 are the
# late-surrender changes. Insurance (take at +3) is handled separately.
INSURANCE_INDEX = 3
DEVIATIONS: tuple[Deviation, ...] = (
    Deviation("16 vs 10", "hard 16", 10, "stand", "hit", 0, "I18"),
    Deviation("15 vs 10", "hard 15", 10, "stand", "hit", 4, "I18"),
    Deviation("10,10 vs 5", "pair TT", 5, "split", "stand", 5, "I18"),
    Deviation("10,10 vs 6", "pair TT", 6, "split", "stand", 4, "I18"),
    Deviation("10 vs 10", "hard 10", 10, "double", "hit", 4, "I18"),
    Deviation("12 vs 3", "hard 12", 3, "stand", "hit", 2, "I18"),
    Deviation("12 vs 2", "hard 12", 2, "stand", "hit", 3, "I18"),
    Deviation("11 vs A", "hard 11", 1, "double", "hit", 1, "I18"),
    Deviation("9 vs 2", "hard 9", 2, "double", "hit", 1, "I18"),
    Deviation("10 vs A", "hard 10", 1, "double", "hit", 4, "I18"),
    Deviation("9 vs 7", "hard 9", 7, "double", "hit", 3, "I18"),
    Deviation("16 vs 9", "hard 16", 9, "stand", "hit", 5, "I18"),
    Deviation("13 vs 2", "hard 13", 2, "stand", "hit", -1, "I18"),
    Deviation("12 vs 4", "hard 12", 4, "stand", "hit", 0, "I18"),
    Deviation("12 vs 5", "hard 12", 5, "stand", "hit", -2, "I18"),
    Deviation("12 vs 6", "hard 12", 6, "stand", "hit", -1, "I18"),
    Deviation("13 vs 3", "hard 13", 3, "stand", "hit", -2, "I18"),
    Deviation("14 vs 10 surrender", "hard 14", 10, "surrender", "hit", 3, "Fab4"),
    Deviation("15 vs 10 surrender", "hard 15", 10, "surrender", "hit", 0, "Fab4"),
    Deviation("15 vs 9 surrender", "hard 15", 9, "surrender", "hit", 2, "Fab4"),
    Deviation("15 vs A surrender", "hard 15", 1, "surrender", "hit", 1, "Fab4"),
)


def deviations_for(hand: str, up: int) -> list[Deviation]:
    return [d for d in DEVIATIONS if d.hand == hand and d.up == up]
