import math

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind
from edge_engine.loop import run_session
from edge_engine.modules.chess import Chess
from edge_engine.modules.chess.board import (
    BLACK,
    START_FEN,
    WHITE,
    Board,
    parse_pgn,
    perft,
    square,
    to_pgn,
    uci,
)
from edge_engine.modules.chess.engine import PST, Engine, evaluate, mate_in, mirror
from edge_engine.modules.chess.lab import PERFT
from edge_engine.modules.chess.module import MATE_IN_ONE
from edge_engine.modules.chess.review import (
    OPERA_GAME,
    classify,
    move_accuracy,
    review_pgn,
    win_percent,
)
from edge_engine.rng import Rng

# --- perft: the "Done when" check ----------------------------------------------------


@pytest.mark.parametrize("name,fen,counts", PERFT, ids=[p[0] for p in PERFT])
def test_perft_matches_published_counts(name, fen, counts):
    board = Board(fen)
    for depth, want in enumerate(counts[:3], 1):
        assert perft(board, depth) == want, (name, depth)
    assert board.fen() == fen  # make / undo left the board exactly as it was


@pytest.mark.slow
@pytest.mark.parametrize("name,fen,counts", PERFT, ids=[p[0] for p in PERFT])
def test_perft_deeper(name, fen, counts):
    depth = 4
    assert perft(Board(fen), depth) == counts[depth - 1]


# --- board mechanics -------------------------------------------------------------------


def random_walk(seed, plies=60):
    rng = Rng(seed)
    b = Board()
    for _ in range(plies):
        moves = b.legal_moves()
        if not moves or b.outcome():
            break
        b.make(rng.choice(moves))
    return b


def test_incremental_hash_and_undo():
    for seed in range(15):
        b = random_walk(seed)
        assert b.hash == b._compute_hash()
        fen = b.fen()
        for m in b.legal_moves():
            b.make(m)
            assert b.hash == b._compute_hash()
            b.undo()
            assert b.fen() == fen


def test_fen_round_trip():
    for _, fen, _ in PERFT:
        assert Board(fen).fen() == fen
    with pytest.raises(ValueError):
        Board("8/8/8/8/8/8/8/8 w - - 0 1")  # no kings


def test_san_round_trips_for_every_legal_move():
    for seed in range(10):
        b = random_walk(seed + 50, plies=30)
        for m in b.legal_moves():
            assert b.parse_san(b.san(m)) == m
            assert b.parse_san(uci(m)) == m


def test_san_details():
    b = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    sans = {b.san(m) for m in b.legal_moves()}
    assert {"O-O", "O-O-O", "Rxa8+", "Rxh8+"} <= sans
    b = Board("7k/4P3/8/8/8/8/8/K7 w - - 0 1")
    assert {"e8=Q+", "e8=R+", "e8=B", "e8=N"} <= {b.san(m) for m in b.legal_moves()}
    b = Board("k7/8/8/8/8/8/8/KN3N2 w - - 0 1")  # two knights can reach d2
    sans = {b.san(m) for m in b.legal_moves()}
    assert {"Nbd2", "Nfd2"} <= sans
    b = Board("7k/8/8/8/8/R7/8/R5K1 w - - 0 1")  # two rooks on the a-file can reach a2
    assert {"R1a2", "R3a2"} <= {b.san(m) for m in b.legal_moves()}


def test_en_passant_and_castling_rights():
    b = Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    m = b.parse_san("exf6")
    b.make(m)
    assert b.sq[square("f5")] == 0  # the captured pawn is gone
    b.undo()
    b = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    b.make(b.parse_san("Ra2"))
    assert b.fen().split()[2] == "Kkq"
    b = Board("r3k2r/8/8/8/8/5r2/8/R3K2R w KQkq - 0 1")  # f1 is attacked: no O-O
    assert "O-O" not in {b.san(m) for m in b.legal_moves()}


def test_outcomes():
    assert Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1").outcome() is None
    mated = Board("R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1")
    assert mated.outcome() == "1-0"
    stalemate = Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert stalemate.outcome() == "1/2-1/2"
    assert Board("8/8/4k3/8/8/3NK3/8/8 w - - 0 1").outcome() == "1/2-1/2"  # K+N v K
    assert Board("8/8/4k3/8/8/3RK3/8/8 w - - 100 80").outcome() == "1/2-1/2"  # 50 moves
    b = Board()
    for san in ("Nf3", "Nf6", "Ng1", "Ng8") * 2:
        b.make(b.parse_san(san))
    assert b.repetitions() == 3 and b.outcome() == "1/2-1/2"


def test_pgn_parsing_and_writing():
    text = '[White "A"]\n[Black "B"]\n1. e4 {best by test} e5 (1... c5 2. Nf3) 2. Nf3 $1 Nc6 1-0'
    headers, moves, result = parse_pgn(text)
    assert headers == {"White": "A", "Black": "B"}
    assert moves == ["e4", "e5", "Nf3", "Nc6"] and result == "1-0"
    assert to_pgn(moves, result) == "1. e4 e5 2. Nf3 Nc6 1-0"


# --- engine ------------------------------------------------------------------------------


def test_piece_square_tables():
    assert PST[1][square("e4")] == 20 and PST[1][square("a2")] == 5
    assert all(
        PST[2][square(f + r)] == PST[2][square("hgfedcba"["abcdefgh".index(f)] + r)]
        for f in "abcd"
        for r in "12345678"
    )
    assert mirror(square("e2")) == square("e7")
    assert evaluate(Board()) == 0
    assert evaluate(Board(START_FEN.replace("RNBQKBNR", "RNB1KBNR"))) < -800  # no white queen


@pytest.mark.parametrize("fen", MATE_IN_ONE)
def test_mate_in_one_puzzles(fen):
    b = Board(fen)
    mates = []
    for m in b.legal_moves():
        b.make(m)
        if b.in_check() and not b.legal_moves():
            mates.append(m)
        b.undo()
    assert mates  # each puzzle really has a mate in one
    r = Engine().search(b, 2)
    assert r.move in mates and mate_in(r.score) == 1


def test_mate_in_two_and_winning_material():
    b = Board("7k/8/8/8/8/8/R7/1R4K1 w - - 0 1")
    assert mate_in(Engine().search(b, 4).score) == 2
    b = Board("rnb1kbnr/pppp1ppp/8/4p1q1/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3")
    r = Engine().search(b, 3)
    assert b.san(r.move) == "Nxg5" and r.score > 600


def test_engine_plays_legal_sensible_games():
    """Against random moves, every engine move is legal and the engine wins material."""
    for seed in (1, 2):
        rng = Rng(seed)
        b = Board()
        engine = Engine()
        for ply in range(60):
            if b.outcome():
                break
            if (ply % 2 == 0) == (seed == 1):
                r = engine.search(b, 2)
                assert r.move in b.legal_moves()
                b.make(r.move)
            else:
                b.make(rng.choice(b.legal_moves()))
        engine_colour = WHITE if seed == 1 else BLACK
        assert b.outcome() in (("1-0" if seed == 1 else "0-1"), None)
        assert b.material() * engine_colour >= 5 or b.outcome()


# --- review --------------------------------------------------------------------------------


def test_lichess_formulas():
    assert win_percent(0) == 50
    assert win_percent(300) + win_percent(-300) == pytest.approx(100)
    assert win_percent(10_000) == pytest.approx(100, abs=1e-6)
    assert move_accuracy(60, 50) == pytest.approx(63.6, abs=0.1)
    assert move_accuracy(60, 40) == pytest.approx(40.0, abs=0.1)
    assert move_accuracy(50, 50) == pytest.approx(100.0, abs=0.01)
    assert move_accuracy(50, 55) == pytest.approx(100.0, abs=0.01)  # gains are not rewarded
    assert [classify(x, False) for x in (1, 3, 7, 12, 30)] == [
        "Excellent",
        "Good",
        "Inaccuracy",
        "Mistake",
        "Blunder",
    ]
    assert classify(40, True) == "Best"
    assert math.isclose(win_percent(-10_000), 0, abs_tol=1e-6)


def test_review_of_the_opera_game():
    headers, review = review_pgn(OPERA_GAME, depth=3)
    assert headers["White"] == "Paul Morphy" and review.result == "1-0"
    assert len(review.moves) == 33
    last = review.moves[-1]
    assert last.san == "Rd8#" and last.label == "Best"
    qb8 = review.moves[-3]
    assert qb8.san == "Qb8+" and qb8.label == "Best"  # the queen sacrifice before mate
    for colour in (WHITE, BLACK):
        assert 0 <= review.accuracy(colour) <= 100


# --- the trainer ----------------------------------------------------------------------------


def perfect(config, seed=1, max_turns=None):
    m = Chess()
    holder = {"n": 0}
    orig = m.questions

    def questions(s):
        holder["s"] = s
        return orig(s)

    m.questions = questions

    def ask(q):
        holder["n"] += 1
        if max_turns and holder["n"] > max_turns:
            from edge_engine.loop import Quit

            raise Quit()
        t = m.truth(holder["s"], q)
        return (max(t, key=t.get) if q.kind is Kind.DECISION else t), 1.0

    return run_session(m, seed=seed, ask=ask, config=config)


def test_drills():
    res = perfect({"mode": "drills", "drills": 6})
    assert res.completed and all(t.score.correct for t in res.turns)
    cats = {t.question.category for t in res.turns}
    assert {"piece-moves", "material", "checking-moves", "mate-in-one"} <= cats


def test_play_to_checkmate_from_a_position():
    res = perfect({"fen": MATE_IN_ONE[0], "score_depth": 2})
    assert res.completed and res.result == 1.0
    assert "Result: 1-0" in res.summary and "PGN: 1. Ra8# 1-0" in res.summary


def test_play_a_few_moves_against_the_engine():
    res = perfect({"depth": 2, "score_depth": 1}, max_turns=3)
    assert not res.completed and len(res.turns) == 3
    assert all(t.question.category == "chess-move" for t in res.turns)


def test_bad_config():
    m = Chess()
    for cfg in ({"mode": "bughouse"}, {"colour": "green"}, {"depth": 0}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_lab_and_cli(tmp_path, monkeypatch, capsys):
    assert main(["lab", "chess", "-o", "perft=2", "-o", "depth=2"]) == 0
    out = capsys.readouterr().out
    assert "MISMATCH" not in out and "Paul Morphy" in out
    pgn = tmp_path / "g.pgn"
    pgn.write_text("1. f3 e5 2. g4 Qh4# 0-1")
    assert main(["lab", "chess", "-o", "perft=1", "-o", f"pgn={pgn}"]) == 0
    assert "Qh4#" in capsys.readouterr().out
    answers = iter(["e2e4", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert (
        main(["play", "chess", "--seed", "1", "-o", "depth=1", "--db", str(tmp_path / "h.db")]) == 0
    )
    assert "You play e4" in capsys.readouterr().out
