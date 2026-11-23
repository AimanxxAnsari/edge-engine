"""Chess board on a 0x88 grid: legal moves, make / undo, FEN, SAN, PGN, perft.

Square s = 16 × rank + file (rank 0 = the first rank). s & 0x88 != 0 means off the board.
Pieces: white positive, black negative; 1 pawn, 2 knight, 3 bishop, 4 rook, 5 queen, 6 king.
A move is an int: from | to << 7 | promotion << 14 | flags << 17.
"""

from __future__ import annotations

import re

from ...rng import Rng

WHITE, BLACK = 1, -1
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
EP, CASTLE, DOUBLE = 1, 2, 4  # move flags

KNIGHT_STEPS = (33, 31, 18, 14, -33, -31, -18, -14)
KING_STEPS = (1, -1, 16, -16, 17, 15, -17, -15)
DIAGONALS = (17, 15, -17, -15)
LINES = (1, -1, 16, -16)

PIECE_LETTERS = " PNBRQK"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Castling rights: 1 white king side, 2 white queen side, 4 black king side, 8 black queen side.
CASTLE_MASK = [15] * 128
CASTLE_MASK[0x04] = 15 & ~3  # e1
CASTLE_MASK[0x00] = 15 & ~2  # a1
CASTLE_MASK[0x07] = 15 & ~1  # h1
CASTLE_MASK[0x74] = 15 & ~12  # e8
CASTLE_MASK[0x70] = 15 & ~8  # a8
CASTLE_MASK[0x77] = 15 & ~4  # h8


def square(name: str) -> int:
    return (int(name[1]) - 1) * 16 + "abcdefgh".index(name[0])


def square_name(s: int) -> str:
    return "abcdefgh"[s & 7] + str((s >> 4) + 1)


def encode(frm: int, to: int, promo: int = 0, flags: int = 0) -> int:
    return frm | (to << 7) | (promo << 14) | (flags << 17)


def move_from(m: int) -> int:
    return m & 127


def move_to(m: int) -> int:
    return (m >> 7) & 127


def move_promo(m: int) -> int:
    return (m >> 14) & 7


def move_flags(m: int) -> int:
    return m >> 17


def uci(m: int) -> str:
    promo = move_promo(m)
    return (
        square_name(move_from(m)) + square_name(move_to(m)) + ("nbrq"[promo - 2] if promo else "")
    )


def _zobrist() -> tuple[list[list[int]], int, list[int], list[int]]:
    rng = Rng(20251123)
    pieces = [[rng.next_u64() for _ in range(128)] for _ in range(13)]  # index piece + 6
    side = rng.next_u64()
    castling = [rng.next_u64() for _ in range(16)]
    ep = [rng.next_u64() for _ in range(8)]
    return pieces, side, castling, ep


Z_PIECE, Z_SIDE, Z_CASTLE, Z_EP = _zobrist()


class Board:
    def __init__(self, fen: str = START_FEN) -> None:
        self.set_fen(fen)

    # --- FEN ------------------------------------------------------------------------

    def set_fen(self, fen: str) -> None:
        parts = fen.split()
        if len(parts) < 4:
            raise ValueError(f"bad FEN: {fen!r}")
        self.sq = [0] * 128
        self.kings = {WHITE: -1, BLACK: -1}
        rows = parts[0].split("/")
        if len(rows) != 8:
            raise ValueError(f"bad FEN board: {parts[0]!r}")
        for i, row in enumerate(rows):
            rank, file = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    file += int(ch)
                    continue
                kind = PIECE_LETTERS.index(ch.upper())
                if kind <= 0 or file > 7:
                    raise ValueError(f"bad FEN board: {parts[0]!r}")
                piece = kind if ch.isupper() else -kind
                s = rank * 16 + file
                self.sq[s] = piece
                if kind == KING:
                    self.kings[WHITE if piece > 0 else BLACK] = s
                file += 1
        if -1 in self.kings.values():
            raise ValueError("both kings are needed")
        self.side = WHITE if parts[1] == "w" else BLACK
        self.castling = sum(b for c, b in zip("KQkq", (1, 2, 4, 8), strict=True) if c in parts[2])
        self.ep = -1 if parts[3] == "-" else square(parts[3])
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1
        self.stack: list[tuple] = []
        self.hash = self._compute_hash()
        self.history = [self.hash]

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for file in range(8):
                p = self.sq[rank * 16 + file]
                if p == 0:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                letter = PIECE_LETTERS[abs(p)]
                row += letter if p > 0 else letter.lower()
            rows.append(row + (str(empty) if empty else ""))
        rights = "".join(c for c, b in zip("KQkq", (1, 2, 4, 8), strict=True) if self.castling & b)
        ep = square_name(self.ep) if self.ep >= 0 else "-"
        side = "w" if self.side == WHITE else "b"
        return f"{'/'.join(rows)} {side} {rights or '-'} {ep} {self.halfmove} {self.fullmove}"

    def _compute_hash(self) -> int:
        h = 0
        for s in range(128):
            if not s & 0x88 and self.sq[s]:
                h ^= Z_PIECE[self.sq[s] + 6][s]
        if self.side == BLACK:
            h ^= Z_SIDE
        h ^= Z_CASTLE[self.castling]
        if self.ep >= 0:
            h ^= Z_EP[self.ep & 7]
        return h

    # --- attacks ----------------------------------------------------------------------

    def attacked(self, s: int, by: int) -> bool:
        """Is square s attacked by side `by`?"""
        sq = self.sq
        if by == WHITE:
            for a in (s - 15, s - 17):
                if not a & 0x88 and sq[a] == PAWN:
                    return True
        else:
            for a in (s + 15, s + 17):
                if not a & 0x88 and sq[a] == -PAWN:
                    return True
        knight, king = by * KNIGHT, by * KING
        for d in KNIGHT_STEPS:
            a = s + d
            if not a & 0x88 and sq[a] == knight:
                return True
        for d in KING_STEPS:
            a = s + d
            if not a & 0x88 and sq[a] == king:
                return True
        bishop, rook, queen = by * BISHOP, by * ROOK, by * QUEEN
        for d in DIAGONALS:
            a = s + d
            while not a & 0x88:
                p = sq[a]
                if p:
                    if p == bishop or p == queen:
                        return True
                    break
                a += d
        for d in LINES:
            a = s + d
            while not a & 0x88:
                p = sq[a]
                if p:
                    if p == rook or p == queen:
                        return True
                    break
                a += d
        return False

    def in_check(self, side: int | None = None) -> bool:
        side = self.side if side is None else side
        return self.attacked(self.kings[side], -side)

    # --- move generation ----------------------------------------------------------------

    def pseudo_moves(self, captures_only: bool = False) -> list[int]:
        out: list[int] = []
        sq, me = self.sq, self.side
        for s in range(128):
            if s & 0x88:
                continue
            p = sq[s] * me
            if p <= 0:
                continue
            if p == PAWN:
                self._pawn_moves(s, out, captures_only)
            elif p == KNIGHT or p == KING:
                for d in KNIGHT_STEPS if p == KNIGHT else KING_STEPS:
                    t = s + d
                    if t & 0x88:
                        continue
                    q = sq[t] * me
                    if q < 0 or (q == 0 and not captures_only):
                        out.append(s | (t << 7))
                if p == KING and not captures_only:
                    self._castles(s, out)
            else:
                dirs = DIAGONALS if p == BISHOP else LINES if p == ROOK else DIAGONALS + LINES
                for d in dirs:
                    t = s + d
                    while not t & 0x88:
                        q = sq[t] * me
                        if q > 0:
                            break
                        if q < 0:
                            out.append(s | (t << 7))
                            break
                        if not captures_only:
                            out.append(s | (t << 7))
                        t += d
        return out

    def _pawn_moves(self, s: int, out: list[int], captures_only: bool) -> None:
        sq, me = self.sq, self.side
        fwd = 16 * me
        rank = s >> 4
        last = 6 if me == WHITE else 1  # rank from which a push promotes
        start = 1 if me == WHITE else 6
        t = s + fwd
        if not captures_only and not t & 0x88 and sq[t] == 0:
            if rank == last:
                for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
                    out.append(encode(s, t, promo))
            else:
                out.append(s | (t << 7))
                t2 = t + fwd
                if rank == start and sq[t2] == 0:
                    out.append(encode(s, t2, 0, DOUBLE))
        for side_step in (-1, 1):
            t = s + fwd + side_step
            if t & 0x88:
                continue
            if sq[t] * me < 0:
                if rank == last:
                    for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
                        out.append(encode(s, t, promo))
                else:
                    out.append(s | (t << 7))
            elif t == self.ep:
                out.append(encode(s, t, 0, EP))

    def _castles(self, s: int, out: list[int]) -> None:
        sq, me = self.sq, self.side
        home = 0x04 if me == WHITE else 0x74
        if s != home or self.in_check():
            return
        k_right, q_right = (1, 2) if me == WHITE else (4, 8)
        if self.castling & k_right and sq[s + 1] == 0 and sq[s + 2] == 0:
            if (
                sq[s + 3] == me * ROOK
                and not self.attacked(s + 1, -me)
                and not self.attacked(s + 2, -me)
            ):
                out.append(encode(s, s + 2, 0, CASTLE))
        if self.castling & q_right and sq[s - 1] == 0 and sq[s - 2] == 0 and sq[s - 3] == 0:
            if (
                sq[s - 4] == me * ROOK
                and not self.attacked(s - 1, -me)
                and not self.attacked(s - 2, -me)
            ):
                out.append(encode(s, s - 2, 0, CASTLE))

    def legal_moves(self) -> list[int]:
        out = []
        me = self.side
        for m in self.pseudo_moves():
            self.make(m)
            if not self.attacked(self.kings[me], -me):
                out.append(m)
            self.undo()
        return out

    def legal_captures(self) -> list[int]:
        out = []
        me = self.side
        for m in self.pseudo_moves(captures_only=True):
            self.make(m)
            if not self.attacked(self.kings[me], -me):
                out.append(m)
            self.undo()
        return out

    # --- make / undo ------------------------------------------------------------------

    def make(self, m: int) -> None:
        sq = self.sq
        frm, to = m & 127, (m >> 7) & 127
        promo, flags = (m >> 14) & 7, m >> 17
        me = self.side
        piece = sq[frm]
        captured = sq[to]
        cap_sq = to
        if flags & EP:
            cap_sq = to - 16 * me
            captured = sq[cap_sq]
        self.stack.append((m, captured, cap_sq, self.castling, self.ep, self.halfmove, self.hash))
        h = self.hash ^ Z_CASTLE[self.castling] ^ Z_SIDE
        if self.ep >= 0:
            h ^= Z_EP[self.ep & 7]
        if captured:
            h ^= Z_PIECE[captured + 6][cap_sq]
            sq[cap_sq] = 0
        h ^= Z_PIECE[piece + 6][frm]
        sq[frm] = 0
        placed = promo * me if promo else piece
        sq[to] = placed
        h ^= Z_PIECE[placed + 6][to]
        if piece * me == KING:
            self.kings[me] = to
            if flags & CASTLE:
                rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
                rook = sq[rf]
                sq[rf], sq[rt] = 0, rook
                h ^= Z_PIECE[rook + 6][rf] ^ Z_PIECE[rook + 6][rt]
        self.castling &= CASTLE_MASK[frm] & CASTLE_MASK[to]
        h ^= Z_CASTLE[self.castling]
        if flags & DOUBLE:
            self.ep = frm + 16 * me
            h ^= Z_EP[self.ep & 7]
        else:
            self.ep = -1
        self.halfmove = 0 if (piece * me == PAWN or captured) else self.halfmove + 1
        if me == BLACK:
            self.fullmove += 1
        self.side = -me
        self.hash = h
        self.history.append(h)

    def undo(self) -> None:
        m, captured, cap_sq, castling, ep, halfmove, h = self.stack.pop()
        self.history.pop()
        sq = self.sq
        frm, to = m & 127, (m >> 7) & 127
        promo, flags = (m >> 14) & 7, m >> 17
        self.side = me = -self.side
        piece = PAWN * me if promo else sq[to]
        sq[frm] = piece
        sq[to] = 0
        if captured:
            sq[cap_sq] = captured
        if piece * me == KING:
            self.kings[me] = frm
            if flags & CASTLE:
                rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
                sq[rf], sq[rt] = sq[rt], 0
        if me == BLACK:
            self.fullmove -= 1
        self.castling, self.ep, self.halfmove, self.hash = castling, ep, halfmove, h

    # --- game state ---------------------------------------------------------------------

    def is_capture(self, m: int) -> bool:
        return bool(self.sq[move_to(m)]) or bool(move_flags(m) & EP)

    def repetitions(self) -> int:
        return self.history.count(self.hash)

    def insufficient_material(self) -> bool:
        minors = 0
        for s in range(128):
            if s & 0x88:
                continue
            p = abs(self.sq[s])
            if p in (PAWN, ROOK, QUEEN):
                return False
            if p in (KNIGHT, BISHOP):
                minors += 1
        return minors <= 1

    def outcome(self) -> str | None:
        """'1-0', '0-1', '1/2-1/2' or None while the game goes on."""
        if not self.legal_moves():
            if self.in_check():
                return "0-1" if self.side == WHITE else "1-0"
            return "1/2-1/2"
        if self.halfmove >= 100 or self.repetitions() >= 3 or self.insufficient_material():
            return "1/2-1/2"
        return None

    def material(self) -> int:
        """White minus black, in pawns: 1, 3, 3, 5, 9."""
        values = (0, 1, 3, 3, 5, 9, 0)
        return sum(
            values[abs(p)] * (1 if p > 0 else -1)
            for s, p in enumerate(self.sq)
            if not s & 0x88 and p
        )

    def pieces(self, side: int) -> list[tuple[int, int]]:
        return [(s, p) for s, p in enumerate(self.sq) if not s & 0x88 and p * side > 0]

    # --- SAN ------------------------------------------------------------------------------

    def san(self, m: int) -> str:
        frm, to, promo, flags = move_from(m), move_to(m), move_promo(m), move_flags(m)
        piece = abs(self.sq[frm])
        if flags & CASTLE:
            text = "O-O" if to > frm else "O-O-O"
        else:
            capture = self.is_capture(m)
            if piece == PAWN:
                text = (square_name(frm)[0] + "x" if capture else "") + square_name(to)
                if promo:
                    text += "=" + PIECE_LETTERS[promo]
            else:
                text = PIECE_LETTERS[piece]
                rivals = [
                    o
                    for o in self.legal_moves()
                    if o != m and move_to(o) == to and abs(self.sq[move_from(o)]) == piece
                ]
                if rivals:
                    same_file = any(move_from(o) & 7 == frm & 7 for o in rivals)
                    same_rank = any(move_from(o) >> 4 == frm >> 4 for o in rivals)
                    if not same_file:
                        text += square_name(frm)[0]
                    elif not same_rank:
                        text += square_name(frm)[1]
                    else:
                        text += square_name(frm)
                text += ("x" if capture else "") + square_name(to)
        self.make(m)
        if self.in_check():
            text += "#" if not self.legal_moves() else "+"
        self.undo()
        return text

    def parse_san(self, text: str) -> int:
        """The legal move written as SAN (or UCI) in this position."""
        clean = re.sub(r"[+#!?]+$", "", text.strip()).replace("0-0-0", "O-O-O")
        clean = clean.replace("0-0", "O-O")
        legal = self.legal_moves()
        for m in legal:
            if uci(m) == clean:
                return m
        for m in legal:
            if re.sub(r"[+#]$", "", self.san(m)) == clean:
                return m
        raise ValueError(f"illegal or unknown move {text!r} in {self.fen()}")


# --- perft and PGN -------------------------------------------------------------------------


def perft(board: Board, depth: int) -> int:
    if depth == 0:
        return 1
    moves = board.legal_moves()
    if depth == 1:
        return len(moves)
    total = 0
    for m in moves:
        board.make(m)
        total += perft(board, depth - 1)
        board.undo()
    return total


def parse_pgn(text: str) -> tuple[dict[str, str], list[str], str]:
    """(headers, SAN moves, result). Comments, variations and annotations are dropped."""
    headers = dict(re.findall(r'\[(\w+)\s+"([^"]*)"\]', text))
    body = re.sub(r"\[[^\]]*\]", " ", text)
    body = re.sub(r"\{[^}]*\}", " ", body)
    body = re.sub(r";[^\n]*", " ", body)
    while "(" in body:
        body = re.sub(r"\([^()]*\)", " ", body)
    body = re.sub(r"\$\d+", " ", body)
    tokens = body.split()
    result = "*"
    moves = []
    for tok in tokens:
        if tok in ("1-0", "0-1", "1/2-1/2", "*"):
            result = tok
            continue
        tok = re.sub(r"^\d+\.(\.\.)?", "", tok)
        if tok:
            moves.append(tok)
    return headers, moves, result


def to_pgn(sans: list[str], result: str, headers: dict[str, str] | None = None) -> str:
    lines = [f'[{k} "{v}"]' for k, v in (headers or {}).items()]
    body = []
    for i, san in enumerate(sans):
        if i % 2 == 0:
            body.append(f"{i // 2 + 1}.")
        body.append(san)
    body.append(result)
    return "\n".join(lines + ([""] if lines else []) + [" ".join(body)])
