"""Search: alpha-beta negamax, iterative deepening, transposition table, quiescence."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .board import (
    BISHOP,
    BLACK,
    KING,
    KNIGHT,
    PAWN,
    QUEEN,
    ROOK,
    WHITE,
    Board,
    move_from,
    move_promo,
    move_to,
)

MATE = 100_000
INF = 1_000_000
VALUE = (0, 100, 320, 330, 500, 900, 0)

# Piece-square tables from White's side, rank 8 first (the "simplified evaluation function").
PST_TEXT = {
    PAWN: """ 0  0  0  0  0  0  0  0
             50 50 50 50 50 50 50 50
             10 10 20 30 30 20 10 10
              5  5 10 25 25 10  5  5
              0  0  0 20 20  0  0  0
              5 -5-10  0  0-10 -5  5
              5 10 10-20-20 10 10  5
              0  0  0  0  0  0  0  0""",
    KNIGHT: """-50-40-30-30-30-30-40-50
               -40-20  0  0  0  0-20-40
               -30  0 10 15 15 10  0-30
               -30  5 15 20 20 15  5-30
               -30  0 15 20 20 15  0-30
               -30  5 10 15 15 10  5-30
               -40-20  0  5  5  0-20-40
               -50-40-30-30-30-30-40-50""",
    BISHOP: """-20-10-10-10-10-10-10-20
               -10  0  0  0  0  0  0-10
               -10  0  5 10 10  5  0-10
               -10  5  5 10 10  5  5-10
               -10  0 10 10 10 10  0-10
               -10 10 10 10 10 10 10-10
               -10  5  0  0  0  0  5-10
               -20-10-10-10-10-10-10-20""",
    ROOK: """ 0  0  0  0  0  0  0  0
              5 10 10 10 10 10 10  5
             -5  0  0  0  0  0  0 -5
             -5  0  0  0  0  0  0 -5
             -5  0  0  0  0  0  0 -5
             -5  0  0  0  0  0  0 -5
             -5  0  0  0  0  0  0 -5
              0  0  0  5  5  0  0  0""",
    QUEEN: """-20-10-10 -5 -5-10-10-20
              -10  0  0  0  0  0  0-10
              -10  0  5  5  5  5  0-10
               -5  0  5  5  5  5  0 -5
                0  0  5  5  5  5  0 -5
              -10  5  5  5  5  5  0-10
              -10  0  5  0  0  0  0-10
              -20-10-10 -5 -5-10-10-20""",
    KING: """-30-40-40-50-50-40-40-30
             -30-40-40-50-50-40-40-30
             -30-40-40-50-50-40-40-30
             -30-40-40-50-50-40-40-30
             -20-30-30-40-40-30-30-20
             -10-20-20-20-20-20-20-10
              20 20  0  0  0  0 20 20
              20 30 10  0  0 10 30 20""",
}
KING_END_TEXT = """-50-40-30-20-20-30-40-50
                   -30-20-10  0  0-10-20-30
                   -30-10 20 30 30 20-10-30
                   -30-10 30 40 40 30-10-30
                   -30-10 30 40 40 30-10-30
                   -30-10 20 30 30 20-10-30
                   -30-30  0  0  0  0-30-30
                   -50-30-30-30-30-30-30-50"""


def _parse_table(text: str) -> list[int]:
    """Numbers are 3 characters wide; return 128 entries for White (0x88 squares)."""
    rows = [r.strip() for r in text.strip().splitlines()]
    out = [0] * 128
    for i, row in enumerate(rows):
        row = row.rjust(24)
        values = [int(row[j : j + 3]) for j in range(0, 24, 3)]
        rank = 7 - i
        for f, v in enumerate(values):
            out[rank * 16 + f] = v
    return out


PST = {k: _parse_table(v) for k, v in PST_TEXT.items()}
KING_END = _parse_table(KING_END_TEXT)


def mirror(s: int) -> int:
    """The same square seen from Black's side."""
    return (7 - (s >> 4)) * 16 + (s & 7)


def evaluate(board: Board) -> int:
    """Centipawns from the side to move."""
    score = 0
    phase = 0  # non-pawn material, used to blend the king tables
    bishops = {WHITE: 0, BLACK: 0}
    kings = {}
    for s, p in enumerate(board.sq):
        if s & 0x88 or not p:
            continue
        kind, colour = abs(p), (WHITE if p > 0 else BLACK)
        if kind == KING:
            kings[colour] = s
            continue
        if kind == BISHOP:
            bishops[colour] += 1
        if kind in (KNIGHT, BISHOP, ROOK, QUEEN):
            phase += VALUE[kind]
        idx = s if colour == WHITE else mirror(s)
        score += colour * (VALUE[kind] + PST[kind][idx])
    middle = min(phase, 6200) / 6200  # 1 at the start, 0 with no pieces left
    for colour, s in kings.items():
        idx = s if colour == WHITE else mirror(s)
        score += colour * round(middle * PST[KING][idx] + (1 - middle) * KING_END[idx])
    for colour in (WHITE, BLACK):
        if bishops[colour] >= 2:
            score += colour * 30
    return score * board.side


@dataclass
class SearchResult:
    move: int
    score: int  # centipawns from the side to move; ± MATE − plies for mates
    depth: int
    nodes: int
    pv: list[int] = field(default_factory=list)


EXACT, LOWER, UPPER = 0, 1, 2


class Engine:
    def __init__(self, max_nodes: int = 200_000, table_size: int = 1 << 18) -> None:
        self.max_nodes = max_nodes
        self.table: dict[int, tuple[int, int, int, int]] = {}
        self.table_size = table_size
        self.killers: dict[int, list[int]] = {}
        self.history: dict[int, int] = {}
        self.nodes = 0
        self.stopped = False

    # --- ordering ---------------------------------------------------------------------

    def _order(self, board: Board, moves: list[int], best: int, ply: int) -> list[int]:
        sq = board.sq
        killers = self.killers.get(ply, [])

        def key(m: int) -> int:
            if m == best:
                return -10_000_000
            victim = abs(sq[move_to(m)])
            if victim or move_promo(m):
                attacker = abs(sq[move_from(m)])
                return -1_000_000 - VALUE[victim] * 10 + VALUE[attacker] - VALUE[move_promo(m)]
            if m in killers:
                return -500_000
            return -self.history.get(m, 0)

        return sorted(moves, key=key)

    # --- search -------------------------------------------------------------------------

    def quiescence(self, board: Board, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        stand = evaluate(board)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        for m in self._order(board, board.legal_captures(), 0, ply):
            board.make(m)
            score = -self.quiescence(board, -beta, -alpha, ply + 1)
            board.undo()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if self.nodes >= self.max_nodes:
            self.stopped = True
            return 0
        if ply and (board.halfmove >= 100 or board.repetitions() >= 2):
            return 0
        in_check = board.in_check()
        if in_check and ply < 64:
            depth += 1  # check extension: never stop the search while in check
        if depth <= 0:
            return self.quiescence(board, alpha, beta, ply)
        self.nodes += 1
        alpha_start = alpha
        entry = self.table.get(board.hash)
        best_move = 0
        if entry:
            e_depth, e_score, e_flag, best_move = entry
            if e_depth >= depth and ply:
                if e_flag == EXACT:
                    return e_score
                if e_flag == LOWER and e_score >= beta:
                    return e_score
                if e_flag == UPPER and e_score <= alpha:
                    return e_score
        moves = board.legal_moves()
        if not moves:
            return -(MATE - ply) if in_check else 0
        if board.insufficient_material():
            return 0
        best = -INF
        for m in self._order(board, moves, best_move, ply):
            board.make(m)
            score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.undo()
            if self.stopped:
                return 0
            if score > best:
                best, best_move = score, m
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if not board.is_capture(m):
                    k = self.killers.setdefault(ply, [])
                    if m not in k:
                        k.insert(0, m)
                        del k[2:]
                    self.history[m] = self.history.get(m, 0) + depth * depth
                break
        flag = UPPER if best <= alpha_start else LOWER if best >= beta else EXACT
        if len(self.table) > self.table_size:
            self.table.clear()
        self.table[board.hash] = (depth, best, flag, best_move)
        return best

    def principal_variation(self, board: Board, length: int) -> list[int]:
        pv: list[int] = []
        seen = set()
        for _ in range(length):
            entry = self.table.get(board.hash)
            if not entry or not entry[3] or board.hash in seen:
                break
            m = entry[3]
            if m not in board.legal_moves():
                break
            seen.add(board.hash)
            pv.append(m)
            board.make(m)
        for _ in pv:
            board.undo()
        return pv

    def search(self, board: Board, depth: int, time_limit: float | None = None) -> SearchResult:
        """Iterative deepening to `depth` (or until the node or time budget runs out)."""
        self.nodes = 0
        self.stopped = False
        start = time.time()
        moves = board.legal_moves()
        if not moves:
            raise ValueError("no legal moves")
        result = SearchResult(moves[0], 0, 0, 0)
        for d in range(1, depth + 1):
            score = self.negamax(board, d, -INF, INF, 0)
            if self.stopped:
                break
            entry = self.table.get(board.hash)
            move = entry[3] if entry and entry[3] in moves else moves[0]
            result = SearchResult(move, score, d, self.nodes, self.principal_variation(board, d))
            if abs(score) > MATE - 1000:
                break  # a forced mate: deeper search can't change the result
            if time_limit is not None and time.time() - start > time_limit:
                break
        result.nodes = self.nodes
        return result

    def score_moves(self, board: Board, depth: int) -> dict[int, int]:
        """Each legal move's score for the mover, searching the reply to depth − 1."""
        out = {}
        for m in board.legal_moves():
            board.make(m)
            self.nodes = 0
            self.stopped = False
            out[m] = -self.negamax(board, depth - 1, -INF, INF, 1)
            board.undo()
        return out


def centipawns(score: int) -> int:
    """Mate scores as ±10,000, for the win% formula."""
    if score > MATE - 1000:
        return 10_000
    if score < -(MATE - 1000):
        return -10_000
    return score


def mate_in(score: int) -> int | None:
    """Moves to mate for the side to move (negative if being mated), if a mate score."""
    if abs(score) <= MATE - 1000:
        return None
    plies = MATE - abs(score)
    moves = (plies + 1) // 2
    return moves if score > 0 else -moves
