"""Error measures and per-question scoring."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .core import Kind, Question

EPS = 1e-9


def absolute_error(estimate: float, truth: float) -> float:
    return abs(estimate - truth)


def brier(p: float, outcome: int) -> float:
    """(p − o)², where o is 1 if the event happened, else 0. 0 is perfect, 1 is worst."""
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    if outcome not in (0, 1):
        raise ValueError("outcome must be 0 or 1")
    return (p - outcome) ** 2


def mean_brier(pairs: Iterable[tuple[float, int]]) -> float:
    scores = [brier(p, o) for p, o in pairs]
    if not scores:
        raise ValueError("no forecasts")
    return sum(scores) / len(scores)


def interval_hit(lo: float, hi: float, truth: float) -> bool:
    return lo <= truth <= hi


def hit_rate(hits: Iterable[bool]) -> float:
    hits = list(hits)
    if not hits:
        raise ValueError("no intervals")
    return sum(hits) / len(hits)


def interval_score(lo: float, hi: float, truth: float, level: float) -> float:
    """Winkler interval score for a central interval at the given level. Lower is better.

    width + (2/α)·(distance outside the interval), with α = 1 − level.
    Rewards narrow intervals but punishes misses, so a well-calibrated range wins.
    """
    if hi < lo:
        raise ValueError("hi must be >= lo")
    alpha = 1.0 - level
    penalty = 0.0
    if truth < lo:
        penalty = (2.0 / alpha) * (lo - truth)
    elif truth > hi:
        penalty = (2.0 / alpha) * (truth - hi)
    return (hi - lo) + penalty


def ev_lost(evs: Mapping[str, float], chosen: str) -> float:
    """How much EV the chosen action gave up compared with the best one."""
    if chosen not in evs:
        raise ValueError(f"unknown choice {chosen!r}")
    return max(evs.values()) - evs[chosen]


def speed_score(seconds: float, target: float) -> float:
    """1 at or under the target time, then target/seconds."""
    if target <= 0:
        raise ValueError("target must be positive")
    if seconds <= target:
        return 1.0
    return target / seconds


@dataclass(frozen=True)
class Score:
    error: float
    points: float  # 0..1
    correct: bool | None  # None where "correct" has no meaning (forecasts)


def score_answer(question: Question, answer: Any, truth: Any, seconds: float) -> Score:
    """Score one answer according to the question's kind (see docs/log.md, Phase 0 design)."""
    kind = question.kind
    if kind is Kind.POINT:
        err = absolute_error(float(answer), float(truth))
        ok = err <= question.tolerance + EPS
        return Score(err, 1.0 if ok else 0.0, ok)
    if kind is Kind.SPEED:
        err = absolute_error(float(answer), float(truth))
        ok = err <= question.tolerance + EPS
        assert question.target_seconds is not None
        pts = speed_score(seconds, question.target_seconds) if ok else 0.0
        return Score(err, pts, ok)
    if kind is Kind.DECISION:
        lost = ev_lost(truth, answer)
        ok = lost <= EPS
        return Score(lost, 1.0 if ok else 0.0, ok)
    if kind is Kind.PROBABILITY:
        b = brier(float(answer), int(truth))
        return Score(b, 1.0 - b, None)
    if kind is Kind.INTERVAL:
        lo, hi = answer
        hit = interval_hit(lo, hi, float(truth))
        return Score(interval_score(lo, hi, float(truth), question.level), 1.0 if hit else 0.0, hit)
    raise ValueError(f"unknown kind {kind}")
