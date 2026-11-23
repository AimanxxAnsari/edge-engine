"""`edge-engine lab chess`: perft against published counts, engine checks, game review."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...rng import Rng
from .board import Board, perft
from .engine import Engine, mate_in
from .module import MATE_IN_ONE
from .review import OPERA_GAME, render, review_pgn

# Standard perft positions (chessprogramming.org/Perft_Results): name, FEN, counts by depth.
PERFT = (
    (
        "start",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        (20, 400, 8_902, 197_281, 4_865_609),
    ),
    (
        "Kiwipete",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        (48, 2_039, 97_862, 4_085_603),
    ),
    ("position 3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", (14, 191, 2_812, 43_238, 674_624)),
    (
        "position 4",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        (6, 264, 9_467, 422_333),
    ),
    (
        "position 5",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        (44, 1_486, 62_379, 2_103_487),
    ),
    (
        "position 6",
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
        (46, 2_079, 89_890, 3_894_594),
    ),
)


def run(config: Mapping[str, Any], rng: Rng) -> str:
    max_depth = int(config.get("perft", 3))
    out = [
        f"Perft (all legal move sequences) against the published counts, up to depth {max_depth}:"
    ]
    for name, fen, counts in PERFT:
        board = Board(fen)
        cells = []
        for d, want in enumerate(counts[:max_depth], 1):
            t0 = time.time()
            got = perft(board, d)
            mark = "ok" if got == want else f"MISMATCH (published {want:,})"
            cells.append(f"d{d} {got:,} {mark} ({time.time() - t0:.1f}s)")
        out.append(f"  {name:11} " + "; ".join(cells))
    out.append("")
    out.append("Mate-in-one puzzles, engine at depth 2:")
    for fen in MATE_IN_ONE:
        board = Board(fen)
        r = Engine().search(board, 2)
        out.append(f"  {board.san(r.move):7} mate in {mate_in(r.score)}   {fen}")
    board = Board()
    t0 = time.time()
    r = Engine().search(board, 4)
    out.append("")
    out.append(
        f"From the start, depth {r.depth}: {board.san(r.move)} ({r.score:+d} cp, {r.nodes:,} "
        f"nodes, {time.time() - t0:.1f}s)."
    )
    out.append("")
    depth = int(config.get("depth", 3))
    pgn_path = config.get("pgn")
    text = Path(str(pgn_path)).read_text() if pgn_path else OPERA_GAME
    headers, review = review_pgn(text, depth)
    out.append(render(review, headers))
    return "\n".join(out)
