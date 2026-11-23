"""Make a market on a sum of dice or cards, revealed one at a time, against mixed flow."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from . import bots, contract

DEFAULT_N = 4


@dataclass
class MarketState:
    kind: str
    items: list[int]  # all items, hidden until shown
    bots: int
    informed_share: float
    limit: int
    max_width_sd: float
    shown: int = 0
    position: int = 0
    cash: Fraction = Fraction(0)
    trades: list[bots.Trade] = field(default_factory=list)
    quote: tuple[Fraction, Fraction] | None = None
    log: list[str] = field(default_factory=list)
    threshold: int = 0  # for the binary-option question

    @property
    def n(self) -> int:
        return len(self.items)

    @property
    def revealed(self) -> list[int]:
        return self.items[: self.shown]


def half_round(x: float) -> float:
    """Round up to the next 0.5."""
    return math.ceil(x * 2) / 2


def fmt(x: Fraction | float) -> str:
    x = Fraction(x).limit_denominator(10_000) if not isinstance(x, Fraction) else x
    if x.denominator == 1:
        return f"{x.numerator:+d}" if x < 0 else str(x.numerator)
    return f"{float(x):.2f}"


def signed(x: Fraction) -> str:
    return f"{float(x):+.2f}"


class MarketMaking(GameModule):
    name = "market"
    title = "Market Making"

    def init(self, rng: Rng, config: Mapping[str, Any]) -> MarketState:
        kind = str(config.get("contract", "dice"))
        if kind not in contract.KINDS:
            raise ValueError(f"unknown contract {kind!r}; choose dice or cards")
        n = int(config.get("n", DEFAULT_N))
        share = float(config.get("informed", 0.3))
        state_bots = int(config.get("bots", 4))
        limit = int(config.get("limit", 5))
        max_w = float(config.get("max_width", 2.0))
        if not 1 <= n <= 10 or not 0 <= share <= 1 or state_bots < 1 or limit < 1 or max_w <= 0:
            raise ValueError("need 1 <= n <= 10, 0 <= informed <= 1, bots >= 1, limit >= 1")
        self.rng = rng
        if kind == "dice":
            items = [rng.randint(1, 6) for _ in range(n)]
        else:
            deck = [v for v in contract.CARD_VALUES for _ in range(4)]
            items = rng.sample(deck, n)
        mean = contract.fair_value(kind, [], n)
        sd = contract.std_dev(kind, [], n)
        threshold = math.ceil(float(mean) + sd * rng.choice((0.5, 1.0)))
        return MarketState(
            kind=kind,
            items=items,
            bots=state_bots,
            informed_share=share,
            limit=limit,
            max_width_sd=max_w,
            threshold=threshold,
        )

    # --- helpers -------------------------------------------------------------

    def fair(self, s: MarketState) -> Fraction:
        return contract.fair_value(s.kind, s.revealed, s.n)

    def sd(self, s: MarketState) -> float:
        return contract.std_dev(s.kind, s.revealed, s.n)

    def max_width(self, s: MarketState) -> float:
        return max(1.0, half_round(s.max_width_sd * self.sd(s)))

    def mark(self, s: MarketState) -> Fraction:
        return s.cash + s.position * self.fair(s)

    def settle(self, s: MarketState) -> Fraction:
        return Fraction(sum(s.items))

    def _what(self, s: MarketState) -> str:
        if s.kind == "dice":
            return "one die" if s.n == 1 else f"the sum of {s.n} dice"
        return "one card" if s.n == 1 else f"the sum of {s.n} cards"

    # --- game ----------------------------------------------------------------

    def legal_actions(self, s: MarketState) -> list[str]:
        return [] if self.is_terminal(s) else ["trade"]

    def apply(self, s: MarketState, action: str) -> MarketState:
        if action != "trade" or self.is_terminal(s) or s.quote is None:
            raise ValueError("quote first, then trade")
        bid, ask = s.quote
        new = bots.run_round(
            self.rng,
            s.kind,
            s.items,
            s.shown,
            bid,
            ask,
            s.position,
            s.bots,
            s.informed_share,
            s.limit,
            round_no=s.shown,
        )
        s.log = [f"Your market: {fmt(bid)} – {fmt(ask)}."]
        bought = sum(1 for t in new if t.side == 1)
        sold = len(new) - bought
        if not new:
            s.log.append("No trades.")
        else:
            s.log.append(f"You bought {bought} at {fmt(bid)} and sold {sold} at {fmt(ask)}.")
        for t in new:
            s.position += t.side
            s.cash -= t.side * t.price
        s.trades += new
        item = s.items[s.shown]
        s.shown += 1
        s.log.append(
            f"Revealed: {contract.item_label(s.kind, item)}. "
            f"Position {s.position:+d}, cash {fmt(s.cash)}."
        )
        s.quote = None
        return s

    def is_terminal(self, s: MarketState) -> bool:
        return s.shown >= s.n

    def result(self, s: MarketState) -> float:
        """Final P&L."""
        return float(s.cash + s.position * self.settle(s))

    # --- questions -------------------------------------------------------------

    def questions(self, s: MarketState) -> list[Question]:
        r = s.shown
        qs = []
        if r == 0:
            qs.append(
                Question(
                    id="binary",
                    kind=Kind.POINT,
                    prompt=f"Before anything is shown: chance that {self._what(s)} is at least "
                    f"{s.threshold}?",
                    category="binary-option",
                    tolerance=0.03,
                    tip="Count the outcomes at or above the threshold (or use mean and sd: "
                    "one sd above the mean is about 16% for a bell-shaped sum).",
                )
            )
        qs.append(
            Question(
                id=f"r{r}-fair",
                kind=Kind.POINT,
                prompt=f"Fair value of {self._what(s)} now?",
                category="fair-value",
                tolerance=0.05,
                tip="Revealed sum plus the expected value of each hidden item.",
            )
        )
        qs.append(
            Question(
                id=f"r{r}-sd",
                kind=Kind.POINT,
                prompt="Standard deviation of the sum now?",
                category="std-dev",
                tolerance=0.1 * self.sd(s),
                tip="Add the variances of the hidden items, then take the square root.",
            )
        )
        if r > 0 and s.trades:
            qs.append(
                Question(
                    id=f"r{r}-mark",
                    kind=Kind.POINT,
                    prompt="Your P&L marked at the new fair value?",
                    category="mark-to-market",
                    tolerance=0.5,
                    tip="Cash + position × fair value.",
                )
            )
        w = self.max_width(s)
        pos = f"position {s.position:+d}, limit ±{s.limit}"
        qs.append(
            Question(
                id=f"r{r}-quote",
                kind=Kind.INTERVAL,
                prompt=f"Your market, bid and ask (at most {w:g} wide; {pos})?",
                category="quote",
                level=0.5,
                params={"max_width": w},
                tip="Centre on fair value; tighter earns more from noise traders but loses "
                "more to informed ones; when long, shade both prices down.",
            )
        )
        return qs

    def truth(self, s: MarketState, q: Question) -> float:
        c = q.category
        if c == "binary-option":
            return float(contract.prob_at_least(s.kind, s.revealed, s.n, s.threshold))
        if c in ("fair-value", "quote"):
            return float(self.fair(s))
        if c == "std-dev":
            return self.sd(s)
        if c == "mark-to-market":
            return float(self.mark(s))
        raise ValueError(f"unknown question {q.id}")

    def explain(self, s: MarketState, q: Question) -> str:
        c = q.category
        m = s.n - s.shown
        known = sum(s.revealed)
        shown = " ".join(contract.item_label(s.kind, v) for v in s.revealed) or "nothing"
        if c == "binary-option":
            p = contract.prob_at_least(s.kind, s.revealed, s.n, s.threshold)
            return (
                f"From the exact distribution of the sum: P(sum ≥ {s.threshold}) = "
                f"{float(p):.3f}. Mean {fmt(self.fair(s))}, sd {self.sd(s):.2f}."
            )
        if c == "fair-value":
            if s.kind == "dice":
                hidden = fmt(Fraction(7, 2) * m)
                return (
                    f"Shown: {shown} (sum {known}). {m} dice hidden × 3.5 = {hidden}. "
                    f"Fair {fmt(self.fair(s))}."
                )
            r, mean, _ = contract.pool_stats(contract.unseen_cards(s.revealed))
            return (
                f"Shown: {shown} (sum {known}). The {r} unseen cards average {float(mean):.3f}; "
                f"{m} hidden × {float(mean):.3f} = {float(m * mean):.2f}. Fair {fmt(self.fair(s))}."
            )
        if c == "std-dev":
            if s.kind == "dice":
                return (
                    f"Each die has variance 35/12 ≈ 2.917; {m} dice: "
                    f"{float(Fraction(35, 12) * m):.3f}, sd {self.sd(s):.2f}."
                )
            r, _, var = contract.pool_stats(contract.unseen_cards(s.revealed))
            return (
                f"Unseen cards: variance {float(var):.3f} each. {m} drawn without replacement: "
                f"{m} × {float(var):.3f} × ({r} − {m})/({r} − 1) = "
                f"{float(contract.variance(s.kind, s.revealed, s.n)):.3f}, sd {self.sd(s):.2f}."
            )
        if c == "mark-to-market":
            return (
                f"Cash {fmt(s.cash)} + position {s.position:+d} × fair {fmt(self.fair(s))} = "
                f"{fmt(self.mark(s))}."
            )
        if c == "quote":
            f = self.fair(s)
            sd = self.sd(s)
            text = (
                f"Fair value {fmt(f)}, sd {sd:.2f}. Noise traders value it at fair ± up to "
                f"{sd:.2f}; a market {sd:.2f} wide (half-width sd/2) earns the most from "
                "them before counting informed traders."
            )
            if s.position:
                way = "down" if s.position > 0 else "up"
                text += (
                    f" You are {'long' if s.position > 0 else 'short'}: shade both prices {way}."
                )
            return text
        raise ValueError(f"unknown question {q.id}")

    def observe(
        self, s: MarketState, q: Question, answer: Any, score: Score, seconds: float
    ) -> MarketState:
        if q.category == "quote":
            bid, ask = answer
            s.quote = (bots.price(bid), bots.price(ask))
        return s

    # --- text ------------------------------------------------------------------

    def quote_economics(self, s: MarketState, bid: Fraction, ask: Fraction) -> dict[str, float]:
        """Exact expected profit per trader of a quote, by trader type.

        Noise traders value the contract at fair ± up to one sd (uniform). Informed
        traders know the next item; their value is averaged over what it could be.
        """
        f, sd = float(self.fair(s)), self.sd(s)
        a, b = float(ask), float(bid)
        p_buy = min(1.0, max(0.0, (f + sd - a) / (2 * sd))) if sd else float(f > a)
        p_sell = min(1.0, max(0.0, (b - (f - sd)) / (2 * sd))) if sd else float(f < b)
        noise = p_buy * (a - f) + p_sell * (f - b)
        if s.kind == "dice":
            peeks = [(x, 1 / 6) for x in range(1, 7)]
        else:
            counts = contract.unseen_cards(s.revealed)
            total = sum(counts.values())
            peeks = [(v, c / total) for v, c in counts.items() if c]
        informed = 0.0
        for x, w in peeks:
            g = float(contract.informed_value(s.kind, s.revealed, x, s.n))
            if g > a:
                informed += w * (a - g)  # they buy from you below their value
            elif g < b:
                informed += w * (g - b)  # they sell to you above their value
        share = s.informed_share
        return {
            "noise": noise,
            "informed": informed,
            "mixed": (1 - share) * noise + share * informed,
        }

    def judge(self, s: MarketState, q: Question, answer: Any) -> str:
        """Training wheels: what this quote earns per trader, on average."""
        if q.category != "quote" or answer is None:
            return ""
        bid, ask = bots.price(answer[0]), bots.price(answer[1])
        e = self.quote_economics(s, bid, ask)
        half = (float(ask) - float(bid)) / 2 / self.sd(s) if self.sd(s) else 0.0
        return (
            f"half-width {half:.2f} sd. Expected profit per trader: noise {e['noise']:+.2f}, "
            f"informed {e['informed']:+.2f}; with {s.informed_share:.0%} informed, "
            f"{e['mixed']:+.2f} per trader."
        )

    def describe(self, s: MarketState) -> str:
        lines = []
        if s.shown == 0:
            what = (
                "a die is 1-6, so each averages 3.5"
                if s.kind == "dice"
                else "cards are A=1 … K=13 from one deck, no replacement"
            )
            lines.append(
                f"Contract: {self._what(s)} ({what}). One item is revealed per round. "
                f"Bots trade one lot each against your market; about {s.informed_share:.0%} "
                "of them have peeked at the next item."
            )
        lines += s.log
        shown = " ".join(contract.item_label(s.kind, v) for v in s.revealed) or "none"
        lines.append(
            f"Round {s.shown + 1} of {s.n} | shown: {shown} | position {s.position:+d} | "
            f"cash {fmt(s.cash)}"
        )
        return "\n".join(lines)

    def summary(self, s: MarketState) -> str:
        S = self.settle(s)
        items = " ".join(contract.item_label(s.kind, v) for v in s.items)
        lines = list(s.log) + [""]
        lines.append(f"Settlement: {items} = {S}. Position {s.position:+d}, cash {fmt(s.cash)}.")
        b = bots.breakdown(s.trades, S)
        lines.append(
            f"P&L {signed(b.total)} = spread {signed(b.spread)} "
            f"+ adverse selection {signed(b.adverse)} + luck {signed(b.luck)}."
        )
        noise = [t for t in s.trades if not t.informed]
        smart = [t for t in s.trades if t.informed]
        for name, group in (("noise traders", noise), ("informed traders", smart)):
            if group:
                g = bots.breakdown(group, S)
                lines.append(
                    f"  {len(group)} trades with {name}: P&L {signed(g.total)} (spread "
                    f"{signed(g.spread)}, adverse {signed(g.adverse)}, luck {signed(g.luck)})"
                )
        if s.trades:
            lines.append("Trades:")
            for t in s.trades:
                who = (
                    f"informed (saw {contract.item_label(s.kind, t.peek)}, valued {fmt(t.value)})"
                    if t.informed
                    else "noise"
                )
                side = "bought" if t.side == 1 else "sold"
                lines.append(
                    f"  round {t.round + 1}: you {side} at {fmt(t.price)}, "
                    f"fair {fmt(t.fair)}, {who}"
                )
        return "\n".join(lines)
