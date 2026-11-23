"""Backgammon positions and legal move generation, from the side to move.

points[i] is the mover's point i + 1: positive = the mover's checkers, negative = the
opponent's. The mover moves from 24 towards 1 and then off.
"""

from __future__ import annotations

from dataclasses import dataclass

CHECKERS = 15
ROLLS = tuple((a, b) for a in range(1, 7) for b in range(a, 7))  # the 21 distinct rolls


def roll_weight(roll: tuple[int, int]) -> int:
    """How many of the 36 ordered rolls this is: 1 for doubles, 2 otherwise."""
    return 1 if roll[0] == roll[1] else 2


@dataclass(frozen=True)
class Position:
    points: tuple[int, ...]  # 24 entries
    bar: int = 0
    opp_bar: int = 0
    off: int = 0
    opp_off: int = 0

    def key(self) -> tuple:
        return (self.points, self.bar, self.opp_bar, self.off, self.opp_off)

    def flip(self) -> Position:
        """The same position from the other player's side."""
        return Position(
            tuple(-self.points[23 - i] for i in range(24)),
            self.opp_bar,
            self.bar,
            self.opp_off,
            self.off,
        )

    def pips(self) -> int:
        return sum((i + 1) * n for i, n in enumerate(self.points) if n > 0) + 25 * self.bar

    def opp_pips(self) -> int:
        return sum((24 - i) * -n for i, n in enumerate(self.points) if n < 0) + 25 * self.opp_bar

    def checkers(self) -> int:
        return sum(n for n in self.points if n > 0) + self.bar + self.off

    def opp_checkers(self) -> int:
        return sum(-n for n in self.points if n < 0) + self.opp_bar + self.opp_off

    def all_home(self) -> bool:
        return self.bar == 0 and all(n <= 0 for n in self.points[6:])

    def is_valid(self) -> bool:
        return self.checkers() == CHECKERS and self.opp_checkers() == CHECKERS


def start() -> Position:
    pts = [0] * 24
    for point, n in ((24, 2), (13, 5), (8, 3), (6, 5)):
        pts[point - 1] = n
        pts[24 - point] = -n  # the opponent's checkers, mirrored
    return Position(tuple(pts))


@dataclass(frozen=True)
class Move:
    src: int  # 25 = bar; else the point number (1-24)
    dst: int  # 0 = off; else the point number
    hit: bool = False
    die: int = 0  # the die this move used

    def __str__(self) -> str:
        a = "bar" if self.src == 25 else str(self.src)
        b = "off" if self.dst == 0 else str(self.dst)
        return f"{a}/{b}{'*' if self.hit else ''}"


@dataclass(frozen=True)
class Play:
    moves: tuple[Move, ...]
    after: Position  # still from the mover's side

    def __str__(self) -> str:
        return " ".join(str(m) for m in self.moves) if self.moves else "(no move)"


def _single_moves(pos: Position, die: int) -> list[tuple[Move, Position]]:
    pts = pos.points
    out = []
    if pos.bar:
        t = 24 - die  # point 25 − die
        if pts[t] >= -1:
            new = list(pts)
            hit = new[t] == -1
            new[t] = 1 if hit else new[t] + 1
            out.append(
                (
                    Move(25, t + 1, hit, die),
                    Position(tuple(new), pos.bar - 1, pos.opp_bar + hit, pos.off, pos.opp_off),
                )
            )
        return out
    home = pos.all_home()
    highest = max((i for i in range(24) if pts[i] > 0), default=-1)
    for i in range(24):
        if pts[i] <= 0:
            continue
        t = i - die
        if t >= 0:
            if pts[t] >= -1:
                new = list(pts)
                new[i] -= 1
                hit = new[t] == -1
                new[t] = 1 if hit else new[t] + 1
                out.append(
                    (
                        Move(i + 1, t + 1, hit, die),
                        Position(tuple(new), 0, pos.opp_bar + hit, pos.off, pos.opp_off),
                    )
                )
        elif home and (t == -1 or i == highest):
            new = list(pts)
            new[i] -= 1
            off = Position(tuple(new), 0, pos.opp_bar, pos.off + 1, pos.opp_off)
            out.append((Move(i + 1, 0, False, die), off))
    return out


def legal_plays(pos: Position, roll: tuple[int, int]) -> list[Play]:
    """Every distinct legal play for this roll (one per resulting position)."""
    a, b = roll
    orders = [[a] * 4] if a == b else [[a, b], [b, a]]
    found: list[tuple[tuple[Move, ...], Position]] = []

    def rec(p: Position, dice: list[int], moves: tuple[Move, ...]) -> None:
        if not dice:
            found.append((moves, p))
            return
        options = _single_moves(p, dice[0])
        if not options:
            found.append((moves, p))
            return
        for m, nxt in options:
            rec(nxt, dice[1:], moves + (m,))

    for order in orders:
        rec(pos, order, ())
    most = max(len(m) for m, _ in found)
    plays = [(m, p) for m, p in found if len(m) == most]
    if most == 1 and a != b:
        # Only one die can be played: it must be the larger one if that is possible.
        big = max(a, b)
        with_big = [(m, p) for m, p in plays if m[0].die == big]
        if with_big:
            plays = with_big
    unique: dict[tuple, Play] = {}
    for m, p in plays:
        unique.setdefault(p.key(), Play(m, p))
    return list(unique.values())


def result(pos: Position) -> int:
    """From the side that has just moved: 0 if not over, else 1 / 2 / 3 points won.

    Called on the position after the mover's play (before flipping).
    """
    if pos.off < CHECKERS:
        return 0
    if pos.opp_off > 0:
        return 1
    opp_back = pos.opp_bar > 0 or any(n < 0 for n in pos.points[:6])
    return 3 if opp_back else 2  # backgammon or gammon


def render(pos: Position, me: str = "X", them: str = "O") -> str:
    """Board from the mover's side: points 13-24 on top, 12-1 below."""

    def cell(i: int) -> str:
        n = pos.points[i]
        if n == 0:
            return "  ."
        return f"{me if n > 0 else them}{abs(n):>2}"

    top = " ".join(f"{p:>3}" for p in range(13, 25))
    bottom = " ".join(f"{p:>3}" for p in range(12, 0, -1))
    return "\n".join(
        [
            top,
            " ".join(cell(p - 1) for p in range(13, 25)),
            " ".join(cell(p - 1) for p in range(12, 0, -1)),
            bottom,
            f"bar: {me} {pos.bar}  {them} {pos.opp_bar}   off: {me} {pos.off}  {them} {pos.opp_off}"
            f"   pips: {me} {pos.pips()}  {them} {pos.opp_pips()}",
        ]
    )
