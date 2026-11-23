"""Exact bear-off: rolls-to-finish distributions and winning chances, and cube maths."""

from __future__ import annotations

from functools import lru_cache

from .board import ROLLS, Position, legal_plays, roll_weight

MAX_ROLLS = 40


def _home_position(home: tuple[int, ...]) -> Position:
    """A position with only the mover's home-board checkers (1-6) on the board."""
    pts = list(home) + [0] * 18
    off = 15 - sum(home)
    return Position(tuple(pts), off=off, opp_off=15)


@lru_cache(maxsize=200_000)
def finish_distribution(home: tuple[int, ...]) -> tuple[float, ...]:
    """P(all checkers are off after exactly n rolls), n = 0 .. MAX_ROLLS.

    Each roll is played to minimise the expected number of rolls still needed.
    """
    if sum(home) == 0:
        return (1.0,) + (0.0,) * MAX_ROLLS
    out = [0.0] * (MAX_ROLLS + 1)
    pos = _home_position(home)
    for roll in ROLLS:
        best = None
        best_mean = float("inf")
        for play in legal_plays(pos, roll):
            nxt = tuple(play.after.points[:6])
            mean = expected_rolls(nxt)
            if mean < best_mean:
                best, best_mean = nxt, mean
        dist = finish_distribution(best)
        p = roll_weight(roll) / 36
        for n in range(MAX_ROLLS):
            out[n + 1] += p * dist[n]
    return tuple(out)


@lru_cache(maxsize=200_000)
def expected_rolls(home: tuple[int, ...]) -> float:
    if sum(home) == 0:
        return 0.0
    return sum(n * p for n, p in enumerate(finish_distribution(home)))


def win_chance(on_roll: tuple[int, ...], other: tuple[int, ...]) -> float:
    """P(the player on roll finishes first): needs n rolls, the other needs more than n − 1."""
    a = finish_distribution(on_roll)
    b = finish_distribution(other)
    b_cdf = []
    total = 0.0
    for x in b:
        total += x
        b_cdf.append(total)
    return sum(a[n] * (1 - (b_cdf[n - 1] if n >= 1 else 0.0)) for n in range(len(a)))


def pips(home: tuple[int, ...]) -> int:
    return sum((i + 1) * n for i, n in enumerate(home))


# --- the cube (dead cube, money play, no gammons) --------------------------------------


def cube_values(p: float) -> dict[str, float]:
    """Doubler's EV per unit of the current stake, with the opponent's best reply."""
    no_double = 2 * p - 1
    take = 2 * (2 * p - 1)
    drop = 1.0
    return {"no double": no_double, "double": min(take, drop), "if taken": take, "if dropped": drop}


def take_values(p_doubler: float) -> dict[str, float]:
    """Taker's EV: take = 2 × (1 − 2p), drop = −1."""
    return {"take": 2 * (1 - 2 * p_doubler), "drop": -1.0}


def race_rule(leader_pips: int, trailer_pips: int) -> dict[str, object]:
    """The 8-9-12 rule for long races (a rule of thumb, not exact)."""
    lead = (trailer_pips - leader_pips) / leader_pips
    return {
        "lead": lead,
        "double": lead >= 0.08,
        "redouble": lead >= 0.09,
        "take": lead <= 0.12,
    }
