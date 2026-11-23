"""Backgammon bots: random, a hand-written evaluation (0-ply) and a 1-ply search."""

from __future__ import annotations

from collections.abc import Callable

from ...rng import Rng
from .board import ROLLS, Play, Position, legal_plays, result, roll_weight

WEIGHTS = {
    "pips": 0.1,  # per 10 pips of race lead
    "exposure": 1.0,  # per blot, × chance of being hit × how far back a hit sends it
    "home_point": 0.25,  # made points in the home board
    "bar_point": 0.2,  # the 7-point
    "anchor": 0.15,  # made points in the opponent's home board
    "prime": 0.12,  # per point in the longest run of made points
    "opp_bar": 0.35,  # per opponent checker on the bar
    "off": 0.1,  # per checker borne off
}


def _direct_hits(distance: int, roll: tuple[int, int]) -> bool:
    """Can a checker `distance` pips away hit with this roll (ignoring blocks)?"""
    a, b = roll
    if a == b:
        return distance in (a, 2 * a, 3 * a, 4 * a)
    return distance in (a, b, a + b)


def exposure(pos: Position, point: int) -> float:
    """Approximate chance (0-1) that the opponent hits the mover's blot on `point`.

    Fast version for the evaluation: counts rolls ignoring blocked landing points.
    """
    shooters = [i + 1 for i, n in enumerate(pos.points) if n < 0 and i + 1 < point]
    if pos.opp_bar:
        shooters.append(0)  # entering from the bar: the opponent's 'point 0'
    hits = 0
    for roll in ROLLS:
        if any(_direct_hits(point - s, roll) for s in shooters if point - s <= 24):
            hits += roll_weight(roll)
    return hits / 36


def longest_prime(pts: tuple[int, ...]) -> int:
    best = run = 0
    for n in pts:
        run = run + 1 if n >= 2 else 0
        best = max(best, run)
    return best


def evaluate(pos: Position) -> float:
    """Score of a position for the player who has just moved (higher is better)."""
    won = result(pos)
    if won:
        return 100.0 * won
    w = WEIGHTS
    pts = pos.points
    score = w["pips"] * (pos.opp_pips() - pos.pips()) / 10
    contact = any(n < 0 for i, n in enumerate(pts) if any(m > 0 for m in pts[: i + 1])) or (
        pos.opp_bar > 0
    )
    if contact:
        for i, n in enumerate(pts):
            if n == 1:
                score -= w["exposure"] * exposure(pos, i + 1) * (0.5 + (i + 1) / 24)
    score += w["home_point"] * sum(1 for n in pts[:6] if n >= 2)
    score += w["bar_point"] * (pts[6] >= 2)
    score += w["anchor"] * sum(1 for n in pts[18:] if n >= 2)
    score += w["prime"] * longest_prime(pts)
    score += w["opp_bar"] * pos.opp_bar
    score += w["off"] * pos.off
    return score


Chooser = Callable[[Position, tuple[int, int]], Play | None]


def random_bot(rng: Rng) -> Chooser:
    def choose(pos: Position, roll: tuple[int, int]) -> Play | None:
        plays = legal_plays(pos, roll)
        return rng.choice(plays) if plays and plays[0].moves else None

    return choose


def greedy_bot(pos: Position, roll: tuple[int, int]) -> Play | None:
    """0-ply: the play with the best static evaluation."""
    plays = legal_plays(pos, roll)
    if not plays or not plays[0].moves:
        return None
    return max(plays, key=lambda p: evaluate(p.after))


def one_ply_value(after: Position) -> float:
    """Average over the opponent's rolls of minus their best reply's evaluation."""
    if result(after):
        return evaluate(after)
    theirs = after.flip()
    total = 0.0
    for roll in ROLLS:
        replies = legal_plays(theirs, roll)
        best = max(evaluate(p.after) for p in replies)
        total += roll_weight(roll) * -best
    return total / 36


def one_ply_bot(pos: Position, roll: tuple[int, int]) -> Play | None:
    plays = legal_plays(pos, roll)
    if not plays or not plays[0].moves:
        return None
    # Prune with the static evaluation first, then search the best few.
    shortlist = sorted(plays, key=lambda p: -evaluate(p.after))[:6]
    return max(shortlist, key=lambda p: one_ply_value(p.after))


def play_game(
    first: Chooser, second: Chooser, rng: Rng, start: Position | None = None, max_turns: int = 1000
) -> tuple[int, int]:
    """Play one game. Returns (winner 0 or 1, points 1-3)."""
    from .board import start as start_position

    pos = start or start_position()
    players = (first, second)
    turn = 0
    for _ in range(max_turns):
        roll = (rng.randint(1, 6), rng.randint(1, 6))
        play = players[turn](pos, roll)
        after = play.after if play else pos
        won = result(after)
        if won:
            return turn, won
        pos = after.flip()
        turn = 1 - turn
    raise RuntimeError("game did not finish")
