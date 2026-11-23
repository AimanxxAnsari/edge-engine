"""Poker hand evaluation for 5 to 7 cards, written from scratch.

Cards are ints 0-51: rank = c // 4 (0 = deuce ... 12 = ace), suit = c % 4.
`evaluate` returns an int: higher is better. The category sits in the top bits and the
deciding ranks (most important first) in 4-bit slots below it.
"""

from __future__ import annotations

from collections.abc import Sequence

RANKS = "23456789TJQKA"
SUITS = "cdhs"
CATEGORIES = (
    "high card",
    "pair",
    "two pair",
    "three of a kind",
    "straight",
    "flush",
    "full house",
    "four of a kind",
    "straight flush",
)
WHEEL = 1 << 12 | 0b1111  # A, 2, 3, 4, 5 as a rank bit mask


def card(text: str) -> int:
    """'As' -> 51, 'Td' -> 33."""
    if len(text) != 2 or text[0] not in RANKS or text[1] not in SUITS:
        raise ValueError(f"bad card {text!r}")
    return RANKS.index(text[0]) * 4 + SUITS.index(text[1])


def cards(text: str) -> list[int]:
    """'As Kd 7h' -> list of ints."""
    return [card(t) for t in text.split()]


def name(c: int) -> str:
    return RANKS[c // 4] + SUITS[c % 4]


def names(cs: Sequence[int]) -> str:
    return " ".join(name(c) for c in cs)


def _pack(category: int, ranks: Sequence[int]) -> int:
    score = category
    for i in range(5):
        score = (score << 4) | (ranks[i] if i < len(ranks) else 0)
    return score


def category(score: int) -> int:
    return score >> 20


def _straight_high(mask: int) -> int:
    """Highest card of the best straight in a rank bit mask, or -1."""
    for high in range(12, 3, -1):
        run = 0b11111 << (high - 4)
        if mask & run == run:
            return high
    if mask & WHEEL == WHEEL:
        return 3  # five-high
    return -1


def evaluate(hand: Sequence[int]) -> int:
    """Score of the best five-card hand within 5-7 cards."""
    if not 5 <= len(hand) <= 7:
        raise ValueError("need 5 to 7 cards")
    counts = [0] * 13
    by_suit: list[list[int]] = [[], [], [], []]
    for c in hand:
        r = c >> 2
        counts[r] += 1
        by_suit[c & 3].append(r)

    flush_ranks = None
    for ranks in by_suit:
        if len(ranks) >= 5:
            flush_ranks = sorted(ranks, reverse=True)
            break
    if flush_ranks is not None:
        mask = 0
        for r in flush_ranks:
            mask |= 1 << r
        high = _straight_high(mask)
        if high >= 0:
            return _pack(8, [high])

    quads = [r for r in range(12, -1, -1) if counts[r] == 4]
    trips = [r for r in range(12, -1, -1) if counts[r] == 3]
    pairs = [r for r in range(12, -1, -1) if counts[r] == 2]
    singles = [r for r in range(12, -1, -1) if counts[r] == 1]

    if quads:
        q = quads[0]
        kicker = max(r for r in range(13) if counts[r] and r != q)
        return _pack(7, [q, kicker])
    if trips and (len(trips) > 1 or pairs):
        t = trips[0]
        pair = max(trips[1:] + pairs)
        return _pack(6, [t, pair])
    if flush_ranks is not None:
        return _pack(5, flush_ranks[:5])
    mask = 0
    for r in range(13):
        if counts[r]:
            mask |= 1 << r
    high = _straight_high(mask)
    if high >= 0:
        return _pack(4, [high])
    if trips:
        t = trips[0]
        kickers = sorted([r for r in range(13) if counts[r] and r != t], reverse=True)[:2]
        return _pack(3, [t] + kickers)
    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        kicker = max(r for r in range(13) if counts[r] and r not in (p1, p2))
        return _pack(2, [p1, p2, kicker])
    if pairs:
        p = pairs[0]
        return _pack(1, [p] + singles[:3])
    return _pack(0, singles[:5])


def describe(score: int) -> str:
    return CATEGORIES[category(score)]
