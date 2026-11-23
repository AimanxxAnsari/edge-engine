"""The step-by-step Session must play exactly like run_session (and so like the terminal)."""

import pytest

from edge_engine.core import Kind
from edge_engine.loop import Quit, Session, run_session
from edge_engine.modules import get_module
from edge_engine.storage import Store

LIMIT = 40  # answers per game, so long games stay quick

GAMES = [
    ("dice", {"rounds": 4}),
    ("mental", {"mode": "practice", "questions": 12}),
    ("mental", {"mode": "sprint", "seconds": 20}),
    ("kelly", {"flips": 12}),
    ("kelly", {"mode": "unknown", "flips": 22}),
    ("blackjack", {"hands": 12}),
    ("blackjack", {"mode": "count", "hands": 8}),
    ("blackjack", {"mode": "drill"}),
    ("market", {}),
    ("market", {"contract": "cards", "n": 3}),
    ("poker", {"hands": 6}),
    ("poker", {"mode": "leduc", "hands": 4}),
    ("poker", {"mode": "spots", "hands": 3}),
    ("backgammon", {"bot": "random"}),
    ("backgammon", {"mode": "cube", "spots": 4}),
    ("chess", {"depth": 1, "score_depth": 1}),
    ("chess", {"mode": "drills", "drills": 4}),
]


def scripted_answer(module, state, q, n):
    """Deterministic answers: mostly right, every third one wrong."""
    if q.kind is Kind.PROBABILITY:
        return 0.3 if n % 2 else 0.7
    truth = module.truth(state, q)
    wrong = n % 3 == 0
    if q.kind is Kind.DECISION:
        ranked = sorted(truth, key=lambda c: (-truth[c], c))
        return ranked[-1] if wrong else ranked[0]
    if q.kind is Kind.INTERVAL:
        return (truth - 1.5, truth + 0.5) if wrong else (truth - 1.0, truth + 1.0)
    if q.category == "kelly-bet":
        return 0.0 if wrong else truth
    return truth + 1 if wrong else truth


def via_run_session(game, config, seed, store=None, wheels=False):
    module = get_module(game)
    holder = {"n": 0}
    orig = module.questions

    def questions(state):
        holder["state"] = state
        return orig(state)

    module.questions = questions

    def ask(q, aid=None):
        holder["n"] += 1
        if holder["n"] > LIMIT:
            raise Quit()
        state = holder["state"]
        return scripted_answer(module, state, q, holder["n"]), 2.0

    shown, revealed = [], []
    res = run_session(
        module,
        seed,
        ask,
        config=config,
        store=store,
        wheels=wheels,
        show=shown.append,
        reveal=revealed.append,
    )
    return res, shown, revealed


def via_session(game, config, seed, store=None, wheels=False):
    module = get_module(game)
    s = Session(module, seed, config, store=store, wheels=wheels)
    shown, revealed, last_screen, n = [], [], 0, 0
    while not s.done:
        if s.screen_id != last_screen:
            last_screen = s.screen_id
            if s.screen:
                shown.append(s.screen)
        n += 1
        if n > LIMIT:
            s.quit()
            break
        revealed += s.answer(scripted_answer(module, s.state, s.question, n), 2.0)
    return s.finish(), shown, revealed


def fingerprint(res, shown, revealed):
    turns = [
        (t.question.id, repr(t.answer), repr(t.truth), t.score, t.explanation) for t in res.turns
    ]
    order = [(t.question.id, t.score) for t in revealed]
    return turns, order, res.result, res.summary, res.completed, shown


@pytest.mark.parametrize("game,config", GAMES, ids=[f"{g}-{i}" for i, (g, _) in enumerate(GAMES)])
def test_session_plays_exactly_like_run_session(game, config):
    a = fingerprint(*via_run_session(game, config, seed=11))
    b = fingerprint(*via_session(game, config, seed=11))
    assert a == b
    assert a[0], "the game produced no turns"


def test_same_in_training_wheels_and_logging():
    for game, config in (("dice", {"rounds": 3}), ("blackjack", {"hands": 5})):
        sa, sb = Store(":memory:"), Store(":memory:")
        a = fingerprint(*via_run_session(game, config, seed=5, store=sa, wheels=True))
        b = fingerprint(*via_session(game, config, seed=5, store=sb, wheels=True))
        assert a == b
        rows = "SELECT question_id, answer, truth, points FROM answers ORDER BY id"
        assert sa.conn.execute(rows).fetchall() == sb.conn.execute(rows).fetchall()
        names = "SELECT module, ended_at IS NOT NULL FROM sessions"
        assert sa.conn.execute(names).fetchall() == [(f"{game}:wheels", 1)]


def best(s):
    """The right answer to the current question (0.5 for a forecast)."""
    q = s.question
    if q.kind is Kind.PROBABILITY:
        return 0.5
    truth = s.module.truth(s.state, q)
    return max(truth, key=truth.get) if q.kind is Kind.DECISION else truth


def test_session_api():
    s = Session(get_module("dice"), 1, {"rounds": 1})
    assert s.screen and s.screen_id == 1 and s.question is not None and s.aid() is None
    ids = []
    while not s.done:
        ids.append(s.question.id)
        s.answer(best(s))
    assert ids == ["r0-count", "r0-prob", "r0-bet", "r0-forecast"]
    with pytest.raises(ValueError):
        s.answer(1.0)
    res = s.finish()
    assert res.completed and len(res.turns) == 4 and s.finish() is res


def test_forecasts_are_revealed_after_the_action():
    s = Session(get_module("dice"), 2, {"rounds": 2})
    revealed_per_answer = []
    while not s.done:
        revealed_per_answer.append([t.question.id for t in s.answer(best(s))])
    # The forecast is the last question of a round: answering it rolls the dice and
    # reveals it, so the next round's screen appears only after that.
    assert revealed_per_answer[3] == ["r0-forecast"] and revealed_per_answer[7] == ["r1-forecast"]
    assert all(len(r) == 1 for r in revealed_per_answer)


def test_quit_drops_unresolved_forecasts():
    s = Session(get_module("dice"), 3, {"rounds": 2})
    for _ in range(4):
        s.answer(best(s))
    s.answer(10.0)  # first question of round 2
    s.quit()
    res = s.finish()
    assert not res.completed and s.done and len(res.turns) == 5


def test_chess_plays_a_forced_move_for_you():
    """White to move, in check, with exactly one legal move (Kxa2): it is played for you."""
    s = Session(get_module("chess"), 1, {"fen": "k7/8/8/8/8/8/r7/K1r5 w - - 0 1", "depth": 1})
    assert "You have only one legal move: Kxa2." in s.state.log
    assert s.done or len(s.question.choices) >= 2
