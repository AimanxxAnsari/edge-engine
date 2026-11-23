"""Game review: engine evaluations → win% → accuracy and move classes (Lichess formulas)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .board import WHITE, Board, parse_pgn
from .engine import Engine, centipawns

CLASSES = (  # (upper bound on win% lost, name); "Best" is decided separately
    (2.0, "Excellent"),
    (5.0, "Good"),
    (10.0, "Inaccuracy"),
    (15.0, "Mistake"),
    (math.inf, "Blunder"),
)


def win_percent(cp: float) -> float:
    """Lichess: 50 + 50 × (2 / (1 + e^(−0.00368208 × cp)) − 1)."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(before: float, after: float) -> float:
    """Lichess: 103.1668 × e^(−0.04354 × (before − after)) − 3.1669, kept within 0-100."""
    raw = 103.1668 * math.exp(-0.04354 * max(0.0, before - after)) - 3.1669
    return max(0.0, min(100.0, raw))


def classify(loss: float, is_best: bool) -> str:
    if is_best:
        return "Best"
    for bound, name in CLASSES:
        if loss < bound:
            return name
    return "Blunder"


@dataclass
class MoveReview:
    ply: int
    san: str
    best_san: str
    before: float  # win% for the mover with best play
    after: float  # win% for the mover after the move played
    accuracy: float
    label: str

    @property
    def loss(self) -> float:
        return max(0.0, self.before - self.after)


@dataclass
class GameReview:
    moves: list[MoveReview]
    result: str
    depth: int

    def accuracy(self, colour: int) -> float:
        mine = [m.accuracy for m in self.moves if (m.ply % 2 == 0) == (colour == WHITE)]
        return sum(mine) / len(mine) if mine else 100.0

    def counts(self, colour: int) -> dict[str, int]:
        out: dict[str, int] = {}
        for m in self.moves:
            if (m.ply % 2 == 0) == (colour == WHITE):
                out[m.label] = out.get(m.label, 0) + 1
        return out


def review_moves(sans: list[str], depth: int = 2, start_fen: str | None = None) -> GameReview:
    """Search every position once; score each move by the change in the mover's win%."""
    board = Board(start_fen) if start_fen else Board()
    engine = Engine()
    scores, bests, played = [], [], []
    for san in sans:
        r = engine.search(board, depth)
        scores.append(r.score)
        bests.append(r.move)
        m = board.parse_san(san)
        played.append(m)
        board.make(m)
    final = board.outcome()
    if final is None:
        scores.append(engine.search(board, depth).score)
    elif final == "1/2-1/2":
        scores.append(0)
    else:
        scores.append(-100_000)  # the side to move has been mated
    for _ in sans:
        board.undo()
    reviews = []
    for i in range(len(sans)):
        before = win_percent(centipawns(scores[i]))
        after = win_percent(centipawns(-scores[i + 1]))
        best_san = board.san(bests[i])
        is_best = played[i] == bests[i]
        if is_best:
            after = max(after, before)  # the engine's own move loses nothing by definition
        acc = move_accuracy(before, after)
        reviews.append(
            MoveReview(
                i,
                board.san(played[i]),
                best_san,
                before,
                after,
                acc,
                classify(before - after, is_best),
            )
        )
        board.make(played[i])
    return GameReview(reviews, final or "*", depth)


def review_pgn(text: str, depth: int = 2) -> tuple[dict[str, str], GameReview]:
    headers, sans, result = parse_pgn(text)
    review = review_moves(sans, depth, headers.get("FEN"))
    if review.result == "*":
        review.result = result
    return headers, review


def render(review: GameReview, headers: dict[str, str] | None = None) -> str:
    headers = headers or {}
    lines = []
    if headers:
        who = f"{headers.get('White', '?')} – {headers.get('Black', '?')}"
        lines.append(
            f"{who} ({headers.get('Event', '')}, {headers.get('Date', '')}) {review.result}"
        )
    lines.append(f"Review at depth {review.depth} (this engine's opinion, not Stockfish).")
    lines.append(
        f"{'move':>10} {'best':>8} {'win% before':>12} {'after':>6} {'lost':>5} {'acc':>5}  class"
    )
    for m in review.moves:
        num = f"{m.ply // 2 + 1}{'.' if m.ply % 2 == 0 else '...'}"
        lines.append(
            f"{num:>5} {m.san:<6} {m.best_san:>6} {m.before:10.1f} {m.after:8.1f} "
            f"{m.loss:5.1f} {m.accuracy:5.1f}  {m.label}"
        )
    for colour, name in ((WHITE, "White"), (-WHITE, "Black")):
        counts = ", ".join(f"{k} {v}" for k, v in sorted(review.counts(colour).items()))
        lines.append(f"{name}: accuracy {review.accuracy(colour):.1f}% ({counts})")
    return "\n".join(lines)


OPERA_GAME = """[Event "Paris"]
[Site "Paris FRA"]
[Date "1858.??.??"]
[White "Paul Morphy"]
[Black "Duke Karl / Count Isouard"]
[Result "1-0"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""
