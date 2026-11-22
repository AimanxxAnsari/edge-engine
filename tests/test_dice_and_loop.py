from itertools import product

import pytest

from edge_engine.core import Kind
from edge_engine.loop import Quit, run_session
from edge_engine.modules import get_module
from edge_engine.modules.dice import DiceDemo, p_at_least, ways, ways_at_least
from edge_engine.rng import Rng
from edge_engine.storage import Store


def test_ways_match_enumeration():
    sums = [a + b for a, b in product(range(1, 7), repeat=2)]
    for s in range(0, 15):
        assert ways(s) == sums.count(s)
    for k in range(0, 15):
        assert ways_at_least(k) == sum(1 for s in sums if s >= k)
    assert p_at_least(9) == pytest.approx(10 / 36)


def perfect(q):
    k = q.params["k"]
    p = float(p_at_least(k))
    answer = {
        Kind.SPEED: float(ways_at_least(k)),
        Kind.POINT: p,
        Kind.DECISION: "take" if p > 0.5 else "pass",
        Kind.PROBABILITY: p,
    }[q.kind]
    return answer, 1.0


def test_full_loop_with_logging():
    store = Store(":memory:")
    res = run_session(DiceDemo(), seed=42, ask=perfect, config={"rounds": 5}, store=store)
    assert res.completed and len(res.turns) == 20
    assert store.answer_count(res.session_id) == 20
    for t in res.turns:
        if t.question.kind is Kind.PROBABILITY:
            assert t.score.correct is None and t.truth in (0, 1)
        else:
            assert t.score.correct and t.score.points == 1.0
        assert t.explanation
    assert 0 <= res.result <= 5


def test_forecast_is_scored_after_the_roll():
    order = []
    run_session(
        DiceDemo(),
        seed=3,
        ask=perfect,
        config={"rounds": 1},
        reveal=lambda t: order.append(t.question.kind),
    )
    assert order == [Kind.SPEED, Kind.POINT, Kind.DECISION, Kind.PROBABILITY]


def test_same_seed_same_session():
    def run(seed):
        res = run_session(DiceDemo(), seed=seed, ask=perfect, config={"rounds": 6})
        return [(t.question.prompt, t.truth) for t in res.turns]

    assert run(10) == run(10)
    assert run(10) != run(11)


def test_quit_stops_and_closes_session():
    calls = {"n": 0}

    def ask(q):
        calls["n"] += 1
        if calls["n"] == 6:
            raise Quit()
        return perfect(q)

    store = Store(":memory:")
    res = run_session(DiceDemo(), seed=1, ask=ask, config={"rounds": 3}, store=store)
    assert not res.completed
    # Round 1: 4 answers (forecast scored after the roll). Round 2: one scored, forecast dropped.
    assert len(res.turns) == 5
    ended = store.conn.execute("SELECT ended_at FROM sessions").fetchone()[0]
    assert ended is not None


def test_module_rules():
    m = get_module("dice")
    state = m.init(Rng(0), {"rounds": 1})
    assert m.legal_actions(state) == ["roll"]
    with pytest.raises(ValueError):
        m.apply(state, "jump")
    with pytest.raises(ValueError):
        m.truth(state, m.questions(state)[3])  # forecast before the roll
    state = m.apply(state, "roll")
    assert m.is_terminal(state) and m.legal_actions(state) == []
    with pytest.raises(ValueError):
        m.init(Rng(0), {"rounds": 0})
    with pytest.raises(KeyError):
        get_module("nope")
