import pytest

from edge_engine.core import Kind, Question
from edge_engine.scoring import (
    brier,
    ev_lost,
    hit_rate,
    interval_score,
    mean_brier,
    score_answer,
    speed_score,
)


def q(kind, **kw):
    defaults = {"id": "x", "prompt": "?", "category": "c"}
    if kind is Kind.DECISION:
        kw.setdefault("choices", ("a", "b"))
    if kind is Kind.SPEED:
        kw.setdefault("target_seconds", 5.0)
    return Question(kind=kind, **defaults, **kw)


def test_brier():
    assert brier(0.7, 1) == pytest.approx(0.09)
    assert brier(0.7, 0) == pytest.approx(0.49)
    assert mean_brier([(1.0, 1), (0.0, 1)]) == 0.5
    with pytest.raises(ValueError):
        brier(1.2, 1)
    with pytest.raises(ValueError):
        brier(0.5, 2)


def test_interval_score():
    assert interval_score(2, 4, 3, 0.9) == 2
    assert interval_score(2, 4, 5, 0.9) == pytest.approx(2 + 20 * 1)
    assert interval_score(2, 4, 1.5, 0.8) == pytest.approx(2 + 10 * 0.5)
    assert hit_rate([True, False, True, True]) == 0.75


def test_ev_lost_and_speed():
    assert ev_lost({"hit": -0.2, "stand": -0.5}, "stand") == pytest.approx(0.3)
    assert ev_lost({"hit": -0.2, "stand": -0.5}, "hit") == 0
    assert speed_score(3, 5) == 1.0
    assert speed_score(10, 5) == 0.5


def test_score_point():
    s = score_answer(q(Kind.POINT, tolerance=0.02), 0.29, 10 / 36, 4.0)
    assert s.correct and s.points == 1.0
    s = score_answer(q(Kind.POINT, tolerance=0.02), 0.25, 10 / 36, 4.0)
    assert not s.correct and s.points == 0.0
    assert s.error == pytest.approx(10 / 36 - 0.25)


def test_score_point_tolerance_edge_is_inclusive():
    assert score_answer(q(Kind.POINT, tolerance=0.1), 0.3, 0.2, 1.0).correct


def test_score_speed():
    question = q(Kind.SPEED, target_seconds=5.0)
    assert score_answer(question, 10, 10, 2.0).points == 1.0
    assert score_answer(question, 10, 10, 10.0).points == 0.5
    assert score_answer(question, 11, 10, 1.0).points == 0.0


def test_score_decision():
    evs = {"a": 0.1, "b": -0.3}
    assert score_answer(q(Kind.DECISION), "a", evs, 1.0).correct
    s = score_answer(q(Kind.DECISION), "b", evs, 1.0)
    assert not s.correct and s.error == pytest.approx(0.4)


def test_score_probability():
    s = score_answer(q(Kind.PROBABILITY), 0.8, 1, 1.0)
    assert s.correct is None
    assert s.error == pytest.approx(0.04) and s.points == pytest.approx(0.96)


def test_score_interval():
    question = q(Kind.INTERVAL, level=0.9)
    assert score_answer(question, (5, 9), 7, 1.0).correct
    assert not score_answer(question, (5, 9), 10, 1.0).correct


def test_question_validation():
    with pytest.raises(ValueError):
        Question(id="x", kind=Kind.DECISION, prompt="?", category="c", choices=("only",))
    with pytest.raises(ValueError):
        Question(id="x", kind=Kind.SPEED, prompt="?", category="c")
    with pytest.raises(ValueError):
        Question(id="x", kind=Kind.INTERVAL, prompt="?", category="c", level=1.0)
