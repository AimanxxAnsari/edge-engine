"""Dice demo: the smallest module that uses every part of the loop.

Each round a target k is drawn, then two fair dice are rolled. Before the roll you
answer four questions: count the outcomes (speed), give P(sum >= k) (point),
take or pass an even-money bet (decision) and forecast the roll (probability).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from ..core import GameModule, Kind, Question
from ..rng import Rng


def ways(total: int) -> int:
    """Number of (die1, die2) pairs with this sum: 6 − |s − 7| for s in 2..12."""
    return max(0, 6 - abs(total - 7))


def ways_at_least(k: int) -> int:
    return sum(ways(s) for s in range(max(k, 2), 13))


def p_at_least(k: int) -> Fraction:
    return Fraction(ways_at_least(k), 36)


@dataclass(frozen=True)
class DiceState:
    round: int
    rounds: int
    k: int
    last_roll: tuple[int, int] | None = None
    hits: int = 0


class DiceDemo(GameModule):
    name = "dice"
    title = "Dice demo"

    def init(self, rng: Rng, config: Mapping[str, Any]) -> DiceState:
        rounds = int(config.get("rounds", 3))
        if rounds < 1:
            raise ValueError("rounds must be at least 1")
        self.rng = rng
        return DiceState(round=0, rounds=rounds, k=self._draw_k())

    def _draw_k(self) -> int:
        return self.rng.randint(3, 12)

    def legal_actions(self, state: DiceState) -> list[str]:
        return [] if self.is_terminal(state) else ["roll"]

    def apply(self, state: DiceState, action: str) -> DiceState:
        if action != "roll" or self.is_terminal(state):
            raise ValueError(f"illegal action {action!r}")
        roll = (self.rng.randint(1, 6), self.rng.randint(1, 6))
        hit = sum(roll) >= state.k
        nxt = state.round + 1
        return replace(
            state,
            round=nxt,
            k=self._draw_k() if nxt < state.rounds else state.k,
            last_roll=roll,
            hits=state.hits + int(hit),
        )

    def is_terminal(self, state: DiceState) -> bool:
        return state.round >= state.rounds

    def result(self, state: DiceState) -> float:
        """Number of rolls that reached their target."""
        return float(state.hits)

    def describe(self, state: DiceState) -> str:
        return (
            f"Round {state.round + 1} of {state.rounds}. Two fair dice will be rolled. "
            f"Target: a sum of at least {state.k}."
        )

    def questions(self, state: DiceState) -> list[Question]:
        r, k = state.round, state.k
        params = {"k": k}
        return [
            Question(
                id=f"r{r}-count",
                kind=Kind.SPEED,
                prompt=f"How many of the 36 outcomes have a sum of at least {k}?",
                category="dice-counting",
                target_seconds=10.0,
                params=params,
            ),
            Question(
                id=f"r{r}-prob",
                kind=Kind.POINT,
                prompt=f"What is P(sum >= {k})?",
                category="dice-probability",
                tolerance=0.02,
                params=params,
            ),
            Question(
                id=f"r{r}-bet",
                kind=Kind.DECISION,
                prompt=f"Even-money bet: +1 if the sum is at least {k}, -1 if not. Take or pass?",
                category="ev-decision",
                choices=("take", "pass"),
                params=params,
            ),
            Question(
                id=f"r{r}-forecast",
                kind=Kind.PROBABILITY,
                prompt=f"Forecast: the chance that this roll is at least {k}?",
                category="forecast",
                params=params,
            ),
        ]

    def truth(self, state: DiceState, question: Question) -> Any:
        k = question.params["k"]
        p = p_at_least(k)
        if question.kind is Kind.SPEED:
            return float(ways_at_least(k))
        if question.kind is Kind.POINT:
            return float(p)
        if question.kind is Kind.DECISION:
            return {"take": float(2 * p - 1), "pass": 0.0}
        if question.kind is Kind.PROBABILITY:
            if state.last_roll is None:
                raise ValueError("forecast asked for before the roll")
            return int(sum(state.last_roll) >= k)
        raise ValueError(f"unexpected question kind {question.kind}")

    def explain(self, state: DiceState, question: Question) -> str:
        k = question.params["k"]
        n = ways_at_least(k)
        p = p_at_least(k)
        if question.kind is Kind.SPEED:
            parts = " + ".join(str(ways(s)) for s in range(k, 13))
            return f"A sum s can be made 6 - |s - 7| ways. Sums {k}..12: {parts} = {n}."
        if question.kind is Kind.POINT:
            return f"{n} of 36 outcomes, so P = {n}/36 = {float(p):.4f}."
        if question.kind is Kind.DECISION:
            ev = 2 * p - 1
            best = "take" if ev > 0 else "pass"
            return (
                f"EV(take) = p(+1) + (1 - p)(-1) = 2p - 1 = {float(ev):+.4f}; "
                f"EV(pass) = 0. Best: {best}."
            )
        if question.kind is Kind.PROBABILITY:
            assert state.last_roll is not None
            a, b = state.last_roll
            happened = "happened" if a + b >= k else "did not happen"
            return (
                f"Rolled {a} + {b} = {a + b}, so it {happened}. The exact chance was "
                f"{float(p):.4f}; forecasting that scores {float(p * (1 - p)):.4f} Brier "
                f"on average, the best you can do."
            )
        raise ValueError(f"unexpected question kind {question.kind}")
