"""`edge-engine lab backgammon`: shots, move counts, bot matches, bear-off, cube, TD training."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from ...rng import Rng
from . import bearoff, bots, shots
from .board import ROLLS, legal_plays, start

PUBLISHED_SHOTS = (11, 12, 14, 15, 15, 17, 6, 6, 5, 3, 2, 3)


def opening_counts() -> dict[tuple[int, int], int]:
    return {roll: len(legal_plays(start(), roll)) for roll in ROLLS}


def perft2() -> int:
    """Distinct (first play, reply) pairs over all opening rolls and replies."""
    total = 0
    for roll in ROLLS:
        for play in legal_plays(start(), roll):
            theirs = play.after.flip()
            for reply in ROLLS:
                total += len(legal_plays(theirs, reply))
    return total


def match(first, second, games: int, rng: Rng) -> tuple[int, int]:
    """Wins of `first` over `games`, swapping who starts. Returns (wins, points)."""
    wins = points = 0
    for g in range(games):
        if g % 2 == 0:
            winner, pts = bots.play_game(first, second, rng)
            mine = winner == 0
        else:
            winner, pts = bots.play_game(second, first, rng)
            mine = winner == 1
        wins += mine
        points += pts if mine else -pts
    return wins, points


def run(config: Mapping[str, Any], rng: Rng) -> str:
    games = int(config.get("games", 40))
    out = ["Shots with nothing in between (rolls out of 36), computed with the move generator:"]
    table = shots.open_board_table()
    out.append("  distance " + " ".join(f"{d:>3}" for d in range(1, 13)))
    out.append("  computed " + " ".join(f"{table[d]:>3}" for d in range(1, 13)))
    out.append("  table    " + " ".join(f"{n:>3}" for n in PUBLISHED_SHOTS))
    out.append("")
    counts = opening_counts()
    out.append("Distinct legal plays from the opening position, per roll:")
    out.append("  " + "  ".join(f"{a}-{b}:{n}" for (a, b), n in counts.items()))
    out.append(f"  total over the 21 rolls: {sum(counts.values())}")
    out.append("")
    t0 = time.time()
    w, pts = match(bots.greedy_bot, bots.random_bot(rng), games, rng)
    out.append(
        f"Heuristic bot against random: {w} of {games} games, {pts:+d} points "
        f"({time.time() - t0:.1f}s)."
    )
    out.append("")
    out.append("Bear-off (exact, one-sided): expected rolls to finish")
    for home in ((0, 0, 0, 0, 0, 1), (1, 1, 0, 0, 0, 0), (0, 0, 0, 0, 0, 2), (2, 2, 2, 0, 0, 0)):
        out.append(
            f"  {home} (points 1-6): {bearoff.expected_rolls(home):.3f} rolls, "
            f"{bearoff.pips(home)} pips"
        )
    a, b = (0, 0, 0, 0, 0, 2), (0, 0, 0, 0, 0, 1)
    out.append(f"  on roll with {a} against {b}: wins {bearoff.win_chance(a, b):.3f}")
    out.append("")
    out.append("Dead-cube decisions by the doubler's winning chance p:")
    out.append("     p   no double   double (opponent's best)   taker: take / drop")
    for p in (0.5, 0.6, 0.7, 0.75, 0.8, 0.9):
        v = bearoff.cube_values(p)
        t = bearoff.take_values(p)
        out.append(
            f"  {p:.2f}   {v['no double']:+.2f}       {v['double']:+.2f}"
            f"                      {t['take']:+.2f} / {t['drop']:+.2f}"
        )
    train = int(config.get("train", 0))
    if train:
        from .td import DEFAULT_PATH, Network
        from .td import train as td_train

        net = Network.load() if DEFAULT_PATH.exists() else Network()
        t0 = time.time()
        td_train(net, train, rng)
        net.save()
        w, pts = match(net.choose, bots.random_bot(rng), games, rng)
        g, gpts = match(net.choose, bots.greedy_bot, games, rng)
        out += [
            "",
            f"TD network: trained {train} more self-play games (total {net.games}) in "
            f"{time.time() - t0:.0f}s, saved to {DEFAULT_PATH}.",
            f"  against random: {w} of {games}; against the heuristic bot: {g} of {games}.",
        ]
    return "\n".join(out)
