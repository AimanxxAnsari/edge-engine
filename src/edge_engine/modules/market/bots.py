"""Counterparties and the exact P&L breakdown."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from ...rng import Rng
from . import contract


def price(x: float | Fraction) -> Fraction:
    """A typed price as an exact fraction: 9.3 -> 93/10."""
    if isinstance(x, Fraction):
        return x
    return Fraction(x).limit_denominator(10_000)


@dataclass(frozen=True)
class Trade:
    round: int
    side: int  # +1: you bought (the bot sold at your bid); −1: you sold at your ask
    price: Fraction
    fair: Fraction  # public fair value when the trade happened
    value: Fraction  # the trader's own estimate: = fair for noise traders
    informed: bool
    peek: int | None = None  # what the informed trader saw


def decide(value: float | Fraction, bid: Fraction, ask: Fraction) -> int:
    """The bot's trade, as your sign: +1 it sells to you, −1 it buys from you, 0 none."""
    if value > ask:
        return -1
    if value < bid:
        return 1
    return 0


def run_round(
    rng: Rng,
    kind: str,
    items: Sequence[int],
    shown: int,
    bid: Fraction,
    ask: Fraction,
    position: int,
    bots: int,
    informed_share: float,
    limit: int,
    round_no: int = 0,
) -> list[Trade]:
    """Bots arrive one at a time and trade one lot each against a fixed quote."""
    n = len(items)
    revealed = list(items[:shown])
    fair = contract.fair_value(kind, revealed, n)
    sd = contract.std_dev(kind, revealed, n)
    peek = items[shown]
    smart_value = contract.informed_value(kind, revealed, peek, n)
    trades = []
    for _ in range(bots):
        informed = rng.random() < informed_share
        if informed:
            value: Fraction | float = smart_value
        else:
            value = float(fair) + rng.uniform(-sd, sd)
        side = decide(value, bid, ask)
        if side == 0 or abs(position + side) > limit:
            continue
        position += side
        trades.append(
            Trade(
                round=round_no,
                side=side,
                price=bid if side == 1 else ask,
                fair=fair,
                value=smart_value if informed else fair,
                informed=informed,
                peek=peek if informed else None,
            )
        )
    return trades


@dataclass(frozen=True)
class Breakdown:
    spread: Fraction  # s·(F − p): what you earned against fair value
    adverse: Fraction  # s·(G − F): what informed traders took
    luck: Fraction  # s·(S − G): how the rest of the reveals went
    total: Fraction  # s·(S − p)

    def parts_sum(self) -> Fraction:
        return self.spread + self.adverse + self.luck


def breakdown(trades: Sequence[Trade], settle: Fraction) -> Breakdown:
    spread = sum((t.side * (t.fair - t.price) for t in trades), Fraction(0))
    adverse = sum((t.side * (t.value - t.fair) for t in trades), Fraction(0))
    luck = sum((t.side * (settle - t.value) for t in trades), Fraction(0))
    total = sum((t.side * (settle - t.price) for t in trades), Fraction(0))
    return Breakdown(spread, adverse, luck, total)
