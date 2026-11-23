from fractions import Fraction

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind, Question
from edge_engine.loop import Aid, run_session
from edge_engine.modules.backgammon import Backgammon
from edge_engine.modules.dice import DiceDemo
from edge_engine.modules.kelly import CoinFlip
from edge_engine.modules.market import MarketMaking
from edge_engine.modules.mental import MentalMaths
from edge_engine.rng import Rng
from edge_engine.scoring import Score
from edge_engine.storage import Store
from edge_engine.terminal import TerminalUI


def wheels_session(module, config, answer_with_truth=True, seed=1, store=None):
    seen = []

    def ask(q, aid=None):
        assert aid is not None, "training wheels must pass an aid"
        seen.append((q, aid))
        if q.kind is Kind.PROBABILITY:
            return 0.5, 1.0
        if q.kind is Kind.DECISION:
            return max(aid.truth, key=aid.truth.get), 1.0
        return aid.truth, 1.0

    res = run_session(module, seed=seed, ask=ask, config=config, store=store, wheels=True)
    return res, seen


def test_aid_carries_the_truth_but_never_a_forecast_outcome():
    res, seen = wheels_session(DiceDemo(), {"rounds": 2})
    assert res.completed
    for q, aid in seen:
        if q.kind is Kind.PROBABILITY:
            assert aid.truth is None and aid.explanation == ""
        else:
            assert aid.truth is not None and aid.explanation
    assert all(t.score.correct is not False for t in res.turns)


def test_wheels_sessions_are_logged_separately():
    store = Store(":memory:")
    run_session(
        MentalMaths(),
        seed=1,
        ask=lambda q: (0.0, 1.0),
        config={"mode": "practice", "questions": 3},
        store=store,
    )
    wheels_session(MentalMaths(), {"questions": 4}, store=store)
    modules = {r.module for r in store.category_stats()}
    assert modules == {"mental", "mental:wheels"}
    assert sum(r.n for r in store.category_stats("mental")) == 3  # adaptive history: real play only


def test_mental_maths_is_untimed_with_wheels():
    res, seen = wheels_session(MentalMaths(), {"mode": "sprint"})
    assert res.completed and len(res.turns) == 20  # no clock: a fixed set of questions


def test_judges():
    k = CoinFlip()
    s = k.init(Rng(0), {})
    bet_q = [q for q in k.questions(s) if q.category == "kelly-bet"][0]
    assert "Kelly (+20%)" in k.judge(s, bet_q, 5.0)
    assert "still shrinks you" in k.judge(s, bet_q, 12.5)  # 50% of bankroll

    m = MarketMaking()
    ms = m.init(Rng(0), {})
    fair, sd = m.fair(ms), m.sd(ms)
    h = sd / 2
    e = m.quote_economics(ms, Fraction(fair) - bots_price(h), Fraction(fair) + bots_price(h))
    assert e["noise"] == pytest.approx(h * (sd - h) / sd, rel=1e-3)  # h(sd − h)/sd
    e1 = m.quote_economics(ms, Fraction(fair) - 1, Fraction(fair) + 1)
    assert e1["informed"] == pytest.approx(-4 / 6)  # mean of max(0, |x − 3.5| − 1) over a die
    quote_q = [q for q in m.questions(ms) if q.category == "quote"][0]
    assert "per trader" in m.judge(ms, quote_q, (13.0, 15.0))

    b = Backgammon()
    bs = b.init(Rng(3), {})
    play_q = [q for q in b.questions(bs) if q.category == "checker-play"][0]
    lesson = b.lesson(bs, play_q)
    assert "top plays" in lesson and lesson.count("shots") >= 3
    assert "leaves" in b.judge(bs, play_q, play_q.choices[0])


def bots_price(x):
    return Fraction(x).limit_denominator(10_000)


# --- the terminal flow -------------------------------------------------------------------


def make_aid(truth, note=""):
    q = Question(id="x", kind=Kind.POINT, prompt="?", category="c", tolerance=0.0, tip="a tip")

    def judge(answer):
        ok = answer == truth
        return Score(abs(answer - truth), float(ok), ok), note

    return q, Aid(truth, "because maths", "extra lesson", judge)


def run_ui(inputs, question, aid):
    lines = []
    it = iter(inputs)
    ui = TerminalUI(lambda _: next(it), lines.append, clock=lambda: 0.0)
    answer, _, _ = ui.ask(question, aid=aid)
    return answer, "\n".join(lines)


def test_ui_shows_the_lesson_before_asking():
    q, aid = make_aid(4.0)
    answer, out = run_ui(["4"], q, aid)
    assert answer == 4.0
    for text in ("the answer is 4", "because maths", "extra lesson", "tip: a tip"):
        assert text in out


def test_ui_lets_you_keep_or_change_a_wrong_answer():
    q, aid = make_aid(4.0)
    assert run_ui(["5", ""], q, aid)[0] == 5.0  # Enter keeps it
    assert run_ui(["5", "4"], q, aid)[0] == 4.0  # or type another
    assert "would be wrong" in run_ui(["5", ""], q, aid)[1]


def test_ui_offers_a_comparison_when_there_is_feedback():
    q, aid = make_aid(4.0, note="this costs you nothing")
    answer, out = run_ui(["4", "3", ""], q, aid)
    assert answer == 3.0 and "type another answer to compare" in out


def test_cli_wheels_flag(tmp_path, monkeypatch, capsys):
    answers = iter(["12", "", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    db = tmp_path / "h.db"
    assert main(["play", "mental", "--seed", "1", "--wheels", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Training wheels" in out and "learn: the answer is" in out
    main(["stats", "--db", str(db)])
    assert "mental:wheels" in capsys.readouterr().out
