from collections import Counter
from fractions import Fraction

import pytest

from edge_engine.core import Kind
from edge_engine.loop import run_session
from edge_engine.modules import get_module
from edge_engine.modules.mental import MentalMaths, adaptive
from edge_engine.modules.mental.adaptive import CatStats, from_history, probabilities
from edge_engine.modules.mental.questions import (
    CATEGORIES,
    approx,
    explain,
    fmt,
    make_params,
    prompt,
    solve,
    tolerance,
)
from edge_engine.rng import Rng
from edge_engine.storage import CategoryStats, Store
from edge_engine.terminal import parse_answer, show_tip

# --- truth function --------------------------------------------------------


@pytest.mark.parametrize(
    "params,answer",
    [
        ({"op": "+", "a": 347, "b": 486}, 833),
        ({"op": "-", "a": 503, "b": 278}, 225),
        ({"op": "*", "a": 47, "b": 8}, 376),
        ({"op": "/", "a": 672, "b": 8}, 84),
        ({"op": "*", "a": "0.3", "b": "0.7"}, Fraction(21, 100)),
        ({"op": "/", "a": "4.8", "b": "0.6"}, 8),
        ({"op": "+", "a": "3/4", "b": "1/6"}, Fraction(11, 12)),
        ({"op": "pct_of", "pct": "15", "n": 240}, 36),
        ({"op": "pct_of", "pct": "12.5", "n": 80}, 10),
        ({"op": "what_pct", "a": 18, "b": 72}, 25),
        ({"op": "pct_change", "x": 80, "y": 100}, 25),
        ({"op": "pct_change", "x": 200, "y": 150}, -25),
        ({"op": "odds_to_pct", "a": 3, "b": 1}, 25),
        ({"op": "pct_to_odds", "pct": "20"}, 4),
        ({"op": "pot_odds", "pot": 100, "bet": 50}, 25),  # call 50 to win 200
        ({"op": "pot_odds", "pot": 60, "bet": 60}, Fraction(100, 3)),  # pot-sized bet
    ],
)
def test_solve_known_answers(params, answer):
    assert solve(params) == answer


def test_solve_unknown_op():
    with pytest.raises(ValueError):
        solve({"op": "^", "a": 2, "b": 3})


def test_tolerance():
    assert tolerance({"op": "+"}, Fraction(5)) == 0
    assert tolerance({"tol": "0.5"}, Fraction(5)) == 0.5
    assert tolerance({"rel_tol": "0.02"}, Fraction(-1000)) == pytest.approx(20)


def test_formatting():
    assert fmt(Fraction(5)) == "5"
    assert fmt(Fraction(21, 100)) == "0.21"
    assert fmt(Fraction(1, 3)) == "1/3 (≈ 0.3333)"
    assert approx(Fraction(25, 2)) == "= 12.5"
    assert approx(Fraction(200, 3)) == "≈ 66.67"


# --- generators: properties over many draws --------------------------------


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_generated_questions_are_well_formed(category):
    rng = Rng(123)
    for _ in range(300):
        p = make_params(rng, category)
        ans = solve(p)
        assert p["cat"] == category
        assert prompt(p) and explain(p)
        if category in ("add", "sub", "mul", "div"):
            assert ans.denominator == 1 and ans > 0  # whole, positive answers
        if category == "div":
            assert int(p["a"]) % int(p["b"]) == 0
        if category == "mul":
            assert int(p["a"]) % 10 != 0 or int(p["b"]) >= 10
        if category == "decimals":
            assert ans >= 0 and len(fmt(ans)) <= 7  # short, exact decimal
        if category == "fractions":
            assert ans > 0
        if category == "odds" and p["op"] == "odds_to_pct":
            assert int(p["a"]) > int(p["b"])


def test_percent_questions_have_whole_inputs():
    rng = Rng(5)
    for _ in range(300):
        p = make_params(rng, "percent")
        if p["op"] == "what_pct":
            assert isinstance(p["a"], int)
        if p["op"] == "pct_change":
            assert isinstance(p["y"], int)


def test_generation_is_seeded():
    a = [make_params(Rng(9), c) for c in CATEGORIES]
    b = [make_params(Rng(9), c) for c in CATEGORIES]
    assert a == b


# --- adaptive sampling ------------------------------------------------------

TARGETS = {"a": 5.0, "b": 5.0, "c": 5.0}


def test_no_data_is_uniform():
    probs = probabilities(list(TARGETS), {}, TARGETS)
    assert probs == pytest.approx([1 / 3] * 3)


def test_slow_and_wrong_category_gets_more_weight():
    stats = {
        "a": CatStats(n=20, wrong=10, seconds=20 * 15.0),  # slow and wrong
        "b": CatStats(n=20, wrong=1, seconds=20 * 4.0),  # fast and right
    }
    pa, pb, pc = probabilities(list(TARGETS), stats, TARGETS)
    assert pa > pc > pb  # c has no data, so it sits in the middle
    assert sum((pa, pb, pc)) == pytest.approx(1.0)
    assert min(pa, pb, pc) >= adaptive.FLOOR / 3


def test_time_and_errors_both_count():
    slow = {"a": CatStats(n=10, wrong=2, seconds=10 * 12.0)}
    wrong = {"a": CatStats(n=10, wrong=6, seconds=10 * 5.0)}
    base = {"a": CatStats(n=10, wrong=2, seconds=10 * 5.0)}
    p = [probabilities(list(TARGETS), s, TARGETS)[0] for s in (base, slow, wrong)]
    assert p[1] > p[0] and p[2] > p[0]


def test_adaptive_off_is_uniform():
    stats = {"a": CatStats(n=20, wrong=20, seconds=1000.0)}
    assert probabilities(list(TARGETS), stats, TARGETS, adaptive=False) == [1 / 3] * 3


def test_sampling_follows_probabilities():
    weights = [0.5, 0.3, 0.2]
    rng = Rng(77)
    n = 30_000
    counts = Counter(rng.weighted_index(weights) for _ in range(n))
    chi2 = sum((counts[i] - n * w) ** 2 / (n * w) for i, w in enumerate(weights))
    assert chi2 < 13.8  # 99.9th percentile, 2 degrees of freedom
    with pytest.raises(ValueError):
        rng.weighted_index([0, 0])


def test_history_is_capped():
    s = from_history(n=200, accuracy=0.75, mean_seconds=6.0)
    assert s.n == adaptive.HISTORY_CAP
    assert s.wrong == round(50 * 0.25)
    assert s.seconds == pytest.approx(50 * 6.0)
    assert from_history(0, None, 0.0) == CatStats()


def test_session_shifts_towards_weak_category():
    """A player who is slow and wrong on fractions sees more fractions later."""

    def ask(q):
        if q.category == "fractions":
            return 0.0, 30.0  # wrong and slow
        return float(solve(q.params)), 1.0

    res = run_session(
        MentalMaths(),
        seed=4,
        ask=ask,
        config={"mode": "practice", "questions": 300, "categories": "fractions,add,sub"},
    )
    cats = [t.question.category for t in res.turns]
    first, last = cats[:30], cats[-150:]
    assert last.count("fractions") / len(last) > 0.6
    assert first.count("fractions") / len(first) < last.count("fractions") / len(last)


# --- the module and its modes ----------------------------------------------


def right(q):
    return float(solve(q.params)), 2.0


def test_sprint_ends_on_answering_time():
    res = run_session(MentalMaths(), seed=1, ask=right, config={"mode": "sprint"})
    assert len(res.turns) == 60  # 120 s / 2 s
    assert res.result == 60
    assert all(t.question.kind is Kind.SPEED and t.score.correct for t in res.turns)
    assert "score 60" in res.summary


def test_late_answer_is_logged_but_not_counted():
    res = run_session(
        MentalMaths(), seed=1, ask=lambda q: right(q)[:1] + (7.0,), config={"seconds": 20}
    )
    # 7 s per answer: answers end at 7, 14, 21 s; the third is after time ran out.
    assert len(res.turns) == 3 and res.result == 2
    assert "not counted" in res.summary


def test_test_mode_scoring_and_cap():
    calls = {"n": 0}

    def ask(q):
        calls["n"] += 1
        if calls["n"] % 4 == 0:
            return None, 1.0  # skip
        if calls["n"] % 4 == 3:
            return -1.0, 1.0  # wrong
        return float(solve(q.params)), 1.0

    res = run_session(MentalMaths(), seed=2, ask=ask, config={"mode": "test"})
    assert len(res.turns) == 80  # 80 questions in well under 480 s
    assert res.result == 40 - 20  # 40 right, 20 wrong, 20 skipped
    assert "40 right, 20 wrong, 20 skipped" in res.summary


def test_practice_is_untimed():
    res = run_session(
        MentalMaths(), seed=3, ask=lambda q: (0.0, 500.0), config={"mode": "practice"}
    )
    assert len(res.turns) == 20 and res.result <= 20


def test_bad_config():
    m = MentalMaths()
    for cfg in ({"mode": "race"}, {"categories": "add,algebra"}, {"seconds": 0}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_category_filter_and_registry():
    res = run_session(
        get_module("mental"), seed=8, ask=right, config={"categories": ["odds"], "questions": 10}
    )
    assert {t.question.category for t in res.turns} == {"odds"}


def test_history_loads_from_store():
    store = Store(":memory:")
    run_session(
        MentalMaths(),
        seed=5,
        ask=lambda q: (0.0, 20.0) if q.category == "odds" else right(q),
        config={"mode": "practice", "questions": 40},
        store=store,
    )
    m = MentalMaths()
    m.load_history(store.category_stats("mental"))
    assert m.history["odds"].wrong == m.history["odds"].n
    state = m.init(Rng(0), {})
    assert state.stats["odds"] == m.history["odds"]


def test_load_history_ignores_other_categories():
    m = MentalMaths()
    m.load_history([CategoryStats("mental", "gone", 5, 1.0, 1.0, 0.0, 2.0)])
    assert m.history == {}


# --- terminal details -------------------------------------------------------


def test_percent_answers_and_skip():
    m = MentalMaths()
    state = m.init(Rng(0), {"categories": "percent"})
    q = m.questions(state)[0]
    pq = type(q)(**{**q.__dict__, "params": {**q.params, "unit": "percent"}})
    assert parse_answer(pq, "25") == 25 and parse_answer(pq, "25%") == 25
    assert parse_answer(q, "s") is None and parse_answer(q, "skip") is None
    assert parse_answer(q, "−3") == -3


def test_tips_shown_only_when_wrong_slow_or_skipped():
    res = run_session(MentalMaths(), seed=6, ask=lambda q: right(q)[:1] + (1.0,), config={})
    fast_right = res.turns[0]
    assert not show_tip(fast_right)
    slow = run_session(MentalMaths(), seed=6, ask=lambda q: right(q)[:1] + (60.0,), config={})
    assert show_tip(slow.turns[0])
    wrong = run_session(MentalMaths(), seed=6, ask=lambda q: (-5.0, 1.0), config={"seconds": 3})
    assert show_tip(wrong.turns[0])
