"""Chess: play the engine with move-by-move scoring, and exact board-vision drills."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from .board import BLACK, PIECE_LETTERS, WHITE, Board, square_name, to_pgn, uci
from .engine import Engine, centipawns
from .review import classify, move_accuracy, win_percent

MODES = ("play", "drills")
PIECE_NAMES = {1: "pawn", 2: "knight", 3: "bishop", 4: "rook", 5: "queen", 6: "king"}

# Mate-in-one puzzles (each is checked by exhaustive search in the tests).
MATE_IN_ONE = (
    "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
    "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2",
    "6rk/6pp/8/6N1/8/8/8/6K1 w - - 0 1",
    "7k/8/6K1/8/8/8/8/Q7 w - - 0 1",
    "k7/8/1K6/8/8/8/8/7R w - - 0 1",
    "3r2k1/8/8/8/8/8/5PPP/6K1 b - - 0 1",
    "6k1/R7/1R6/8/8/8/8/6K1 w - - 0 1",
)


def render(board: Board, flip: bool = False) -> str:
    ranks = range(8) if flip else range(7, -1, -1)
    files = range(7, -1, -1) if flip else range(8)
    lines = []
    for r in ranks:
        row = []
        for f in files:
            p = board.sq[r * 16 + f]
            letter = PIECE_LETTERS[abs(p)] if p else "."
            row.append(letter if p >= 0 else letter.lower())
        lines.append(f"{r + 1}  {' '.join(row)}")
    lines.append("   " + " ".join("abcdefgh"[f] for f in files))
    side = "White" if board.side == WHITE else "Black"
    lines.append(f"{side} to move. (Upper case = White, lower case = Black.)")
    return "\n".join(lines)


@dataclass
class Drill:
    kind: str  # 'vision' or 'mate'
    fen: str
    piece_square: int = -1


@dataclass
class ChessState:
    mode: str
    board: Board
    hero: int = WHITE
    depth: int = 3
    score_depth: int = 2
    sans: list[str] = field(default_factory=list)
    pending: str | None = None
    log: list[str] = field(default_factory=list)
    result: str | None = None
    reviews: list[tuple[str, float, float, str]] = field(default_factory=list)
    drills: int = 8
    drill_no: int = 0
    drill: Drill | None = None
    right: int = 0
    done: bool = False
    asked: int = 0
    cache: dict[str, dict[str, float]] = field(default_factory=dict)


class Chess(GameModule):
    name = "chess"
    title = "Chess"

    def init(self, rng: Rng, config: Mapping[str, Any]) -> ChessState:
        mode = str(config.get("mode", "play"))
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
        colour = str(config.get("colour", config.get("color", "white")))
        if colour not in ("white", "black"):
            raise ValueError("colour must be white or black")
        depth = int(config.get("depth", 3))
        drills = int(config.get("drills", 8))
        if not 1 <= depth <= 6 or drills < 1:
            raise ValueError("need 1 <= depth <= 6 and drills >= 1")
        self.rng = rng
        self.engine = Engine()
        s = ChessState(
            mode=mode,
            board=Board(str(config["fen"])) if config.get("fen") else Board(),
            hero=WHITE if colour == "white" else BLACK,
            depth=depth,
            score_depth=int(config.get("score_depth", 2)),
            drills=drills,
        )
        if mode == "drills":
            s.drill = self._new_drill(s)
        elif s.board.side != s.hero:
            self._engine_move(s)
        return s

    # --- play --------------------------------------------------------------------------

    def _engine_move(self, s: ChessState) -> None:
        r = self.engine.search(s.board, s.depth)
        san = s.board.san(r.move)
        s.board.make(r.move)
        s.sans.append(san)
        s.log.append(f"Engine plays {san} (depth {r.depth}, {r.nodes:,} nodes).")
        self._check_end(s)

    def _check_end(self, s: ChessState) -> None:
        outcome = s.board.outcome()
        if outcome:
            s.result = outcome
            s.done = True
            why = "checkmate" if s.board.in_check() and outcome != "1/2-1/2" else "draw"
            if outcome == "1/2-1/2" and not s.board.legal_moves():
                why = "stalemate"
            s.log.append(f"Game over: {outcome} ({why}).")

    def _move_values(self, s: ChessState) -> dict[str, float]:
        """Win% for the hero after each legal move (the engine's view at score_depth)."""
        key = s.board.fen()
        if key not in s.cache:
            scores = self.engine.score_moves(s.board, s.score_depth)
            s.cache[key] = {s.board.san(m): win_percent(centipawns(v)) for m, v in scores.items()}
        return s.cache[key]

    # --- drills ------------------------------------------------------------------------

    def _new_drill(self, s: ChessState) -> Drill:
        if s.drill_no % 3 == 2:
            return Drill("mate", self.rng.choice(MATE_IN_ONE))
        while True:
            b = Board()
            for _ in range(self.rng.randint(8, 40)):
                moves = b.legal_moves()
                if not moves or b.outcome():
                    break
                b.make(self.rng.choice(moves))
            if b.outcome() or not b.legal_moves():
                continue
            pieces = [sq for sq, p in b.pieces(b.side) if abs(p) != 1]
            if pieces:
                return Drill("vision", b.fen(), self.rng.choice(pieces))

    # --- the contract --------------------------------------------------------------------

    def legal_actions(self, s: ChessState) -> list[str]:
        return [] if self.is_terminal(s) else ["next"]

    def apply(self, s: ChessState, action: str) -> ChessState:
        if action != "next" or self.is_terminal(s):
            raise ValueError(f"illegal action {action!r}")
        s.asked = 0
        if s.mode == "drills":
            s.drill_no += 1
            if s.drill_no >= s.drills:
                s.done = True
            else:
                s.drill = self._new_drill(s)
            return s
        s.log = []
        m = s.board.parse_san(s.pending)
        s.board.make(m)
        s.sans.append(s.pending)
        s.log.append(f"You play {s.pending}.")
        s.pending = None
        self._check_end(s)
        if not s.done:
            self._engine_move(s)
        return s

    def is_terminal(self, s: ChessState) -> bool:
        return s.done

    def result(self, s: ChessState) -> float:
        if s.mode == "drills":
            return float(s.right)
        if s.result == "1/2-1/2" or s.result is None:
            return 0.5 if s.result else 0.0
        won = (s.result == "1-0") == (s.hero == WHITE)
        return 1.0 if won else 0.0

    def questions(self, s: ChessState) -> list[Question]:
        if s.mode == "play":
            b = s.board
            sans = sorted(b.san(m) for m in b.legal_moves())
            keys = {}
            for m in b.legal_moves():
                san = b.san(m)
                keys[uci(m)] = san
                keys[re.sub(r"[+#]$", "", san)] = san
            return [
                Question(
                    id=f"m{len(s.sans)}",
                    kind=Kind.DECISION,
                    prompt=f"Your move? Legal: {' '.join(sans)}",
                    category="chess-move",
                    choices=tuple(sans),
                    tolerance=2.0,
                    params={"keys": keys, "hint": "SAN like Nf3 or UCI like g1f3"},
                    tip="Check every check, capture and threat, for both sides, before moving.",
                )
            ]
        d = s.drill
        n = s.drill_no
        if d.kind == "mate":
            b = Board(d.fen)
            return [
                Question(
                    id=f"d{n}-mate",
                    kind=Kind.DECISION,
                    prompt="Mate in one: find it.",
                    category="mate-in-one",
                    choices=tuple(sorted(b.san(m) for m in b.legal_moves())),
                    params={
                        "keys": {re.sub(r"[+#]$", "", b.san(m)): b.san(m) for m in b.legal_moves()}
                        | {uci(m): b.san(m) for m in b.legal_moves()},
                        "hint": "SAN like Qh5 or UCI like d1h5",
                    },
                    tip="Look at every check first: which one leaves the king no square?",
                )
            ]
        b = Board(d.fen)
        piece = abs(b.sq[d.piece_square])
        return [
            Question(
                id=f"d{n}-moves",
                kind=Kind.POINT,
                prompt=f"How many legal moves does the {PIECE_NAMES[piece]} on "
                f"{square_name(d.piece_square)} have?",
                category="piece-moves",
                tip="Count each direction, stopping at pieces; remember pins and checks.",
            ),
            Question(
                id=f"d{n}-material",
                kind=Kind.POINT,
                prompt="Material balance, White minus Black (P 1, N 3, B 3, R 5, Q 9)?",
                category="material",
                tip="Count what is off the board for each side; it is usually quicker.",
            ),
            Question(
                id=f"d{n}-checks",
                kind=Kind.POINT,
                prompt="How many legal moves give check?",
                category="checking-moves",
                tip="Go piece by piece: which squares see the enemy king?",
            ),
        ]

    def truth(self, s: ChessState, q: Question) -> Any:
        c = q.category
        if c == "chess-move":
            return self._move_values(s)
        b = Board(s.drill.fen)
        if c == "mate-in-one":
            out = {}
            for m in b.legal_moves():
                b.make(m)
                mate = b.in_check() and not b.legal_moves()
                b.undo()
                out[b.san(m)] = 1.0 if mate else 0.0
            return out
        if c == "piece-moves":
            return float(sum(1 for m in b.legal_moves() if m & 127 == s.drill.piece_square))
        if c == "material":
            return float(b.material())
        if c == "checking-moves":
            return float(sum(1 for m in b.legal_moves() if "+" in b.san(m) or "#" in b.san(m)))
        raise ValueError(f"unknown question {q.id}")

    def explain(self, s: ChessState, q: Question) -> str:
        c = q.category
        if c == "chess-move":
            values = self._move_values(s)
            ranked = sorted(values, key=lambda k: -values[k])[:3]
            top = ", ".join(f"{k} ({values[k]:.0f}%)" for k in ranked)
            return (
                f"Engine view at depth {s.score_depth} (win% for you after each move; "
                f"not Stockfish): {top}."
            )
        b = Board(s.drill.fen)
        if c == "mate-in-one":
            mates = [k for k, v in self.truth(s, q).items() if v]
            return f"Mate: {', '.join(mates)}."
        if c == "piece-moves":
            moves = [b.san(m) for m in b.legal_moves() if m & 127 == s.drill.piece_square]
            return f"{len(moves)}: {' '.join(moves) or '(none)'}."
        if c == "material":
            return f"White minus Black: {b.material():+d}."
        checks = [b.san(m) for m in b.legal_moves() if "+" in b.san(m) or "#" in b.san(m)]
        return f"{len(checks)}: {' '.join(checks) or '(none)'}."

    def observe(
        self, s: ChessState, q: Question, answer: Any, score: Score, seconds: float
    ) -> ChessState:
        s.asked += 1
        s.right += bool(score.correct)
        if q.category == "chess-move":
            s.pending = answer
            values = self._move_values(s)
            best = max(values.values())
            s.reviews.append(
                (
                    answer,
                    best,
                    values[answer],
                    classify(best - values[answer], values[answer] >= best),
                )
            )
        return s

    # --- text -----------------------------------------------------------------------------

    def describe(self, s: ChessState) -> str:
        if s.mode == "drills":
            kind = "Mate in one" if s.drill.kind == "mate" else "Board vision"
            return f"Drill {s.drill_no + 1} of {s.drills}: {kind}.\n" + render(Board(s.drill.fen))
        lines = list(s.log) if s.asked == 0 else []
        lines.append(render(s.board, flip=s.hero == BLACK))
        return "\n".join(lines)

    def summary(self, s: ChessState) -> str:
        if s.mode == "drills":
            return f"Drills: {s.right} right."
        lines = list(s.log) + [""]
        result = s.result or "unfinished"
        lines.append(f"Result: {result}. You played {'White' if s.hero == WHITE else 'Black'}.")
        if s.reviews:
            accs = [move_accuracy(b, a) for _, b, a, _ in s.reviews]
            counts: dict[str, int] = {}
            for *_, label in s.reviews:
                counts[label] = counts.get(label, 0) + 1
            labels = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
            lines.append(
                f"Your accuracy {sum(accs) / len(accs):.1f}% over {len(accs)} moves ({labels}); "
                f"engine depth {s.score_depth}, Lichess formulas."
            )
            worst = sorted(s.reviews, key=lambda r: r[2] - r[1])[:3]
            bad = [f"{san} (−{b - a:.0f}% win)" for san, b, a, _ in worst if b - a >= 5]
            if bad:
                lines.append("Biggest drops: " + ", ".join(bad) + ".")
        lines.append("PGN: " + to_pgn(s.sans, s.result or "*"))
        return "\n".join(lines)
