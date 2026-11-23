"""Counting the rolls that hit a blot, using the real move generator."""

from __future__ import annotations

from .board import ROLLS, Position, legal_plays, roll_weight


def hitting_rolls(pos: Position, point: int) -> list[tuple[int, int]]:
    """The rolls with which the opponent can hit the mover's blot on `point`.

    `pos` is from the side that owns the blot (e.g. just after their play). The count
    uses the opponent's full move generator, so blocks and bar rules are respected.
    """
    if pos.points[point - 1] != 1:
        raise ValueError(f"no blot on point {point}")
    theirs = pos.flip()
    target = 25 - point  # the same point, numbered from the opponent's side
    out = []
    for roll in ROLLS:
        for play in legal_plays(theirs, roll):
            if any(m.hit and m.dst == target for m in play.moves):
                out.append(roll)
                break
    return out


def shots(pos: Position, point: int) -> int:
    """How many of the 36 rolls hit the blot on `point`."""
    return sum(roll_weight(r) for r in hitting_rolls(pos, point))


def blots(pos: Position) -> list[int]:
    """Points (1-24) where the mover has a single checker."""
    return [i + 1 for i, n in enumerate(pos.points) if n == 1]


def any_shot_rolls(pos: Position) -> int:
    """How many of the 36 rolls hit at least one of the mover's blots."""
    targets = {25 - p for p in blots(pos)}
    if not targets:
        return 0
    theirs = pos.flip()
    count = 0
    for roll in ROLLS:
        if any(
            any(m.hit and m.dst in targets for m in play.moves)
            for play in legal_plays(theirs, roll)
        ):
            count += roll_weight(roll)
    return count


def open_board_table() -> dict[int, int]:
    """Shots at distance 1-12 with nothing in between: one hitter, one blot.

    Each side has one checker left on the board (the other 14 are borne off). The
    opponent moves from the mover's low points towards the high ones, so a hitter d pips
    away from a blot on the mover's 13-point sits on the mover's (13 − d)-point.
    """
    table = {}
    blot = 13
    for d in range(1, 13):
        pts = [0] * 24
        pts[blot - 1] = 1
        pts[blot - 1 - d] = -1
        pos = Position(tuple(pts), off=14, opp_off=14)
        table[d] = shots(pos, blot)
    return table
