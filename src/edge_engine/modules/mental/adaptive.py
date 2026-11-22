"""Adaptive category weights: slow and error-prone categories come up more often."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PRIOR_ANSWERS = 2  # pseudo-answers at the target time (time prior)
FLOOR = 0.25  # share of the probability spread uniformly over all categories
HISTORY_CAP = 50  # history counts for at most this many answers per category


@dataclass(frozen=True)
class CatStats:
    n: int = 0  # answers
    wrong: int = 0  # wrong or skipped
    seconds: float = 0.0  # total answering time

    def add(self, ok: bool, seconds: float) -> CatStats:
        return CatStats(self.n + 1, self.wrong + (0 if ok else 1), self.seconds + seconds)


def error_rate(s: CatStats) -> float:
    """Laplace-smoothed: (wrong + 1) / (n + 2). 0.5 with no data."""
    return (s.wrong + 1) / (s.n + 2)


def time_ratio(s: CatStats, target: float) -> float:
    """Smoothed mean time over the target. 1.0 with no data."""
    mean = (s.seconds + PRIOR_ANSWERS * target) / (s.n + PRIOR_ANSWERS)
    return mean / target


def probabilities(
    categories: Sequence[str],
    stats: Mapping[str, CatStats],
    targets: Mapping[str, float],
    adaptive: bool = True,
) -> list[float]:
    """Sampling probability for each category, in the order given."""
    c = len(categories)
    if c == 0:
        raise ValueError("no categories")
    if not adaptive:
        return [1.0 / c] * c
    raw = []
    for name in categories:
        s = stats.get(name, CatStats())
        raw.append(time_ratio(s, targets[name]) * error_rate(s))
    total = sum(raw)
    return [(1 - FLOOR) * r / total + FLOOR / c for r in raw]


def from_history(n: int, accuracy: float | None, mean_seconds: float) -> CatStats:
    """Turn logged totals into CatStats, scaled down to at most HISTORY_CAP answers."""
    if n <= 0:
        return CatStats()
    wrong = 0.0 if accuracy is None else n * (1 - accuracy)
    seconds = n * mean_seconds
    if n > HISTORY_CAP:
        scale = HISTORY_CAP / n
        n, wrong, seconds = HISTORY_CAP, wrong * scale, seconds * scale
    return CatStats(n=n, wrong=round(wrong), seconds=seconds)
