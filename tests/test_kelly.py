import math
from itertools import product

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind
from edge_engine.loop import run_session
from edge_engine.modules.kelly import CoinFlip, kmath, sim
from edge_engine.prob import binomial_pmf, monte_carlo
from edge_engine.rng import Rng
from edge_engine.terminal import ParseError, format_truth, parse_answer

P = 0.6

# --- exact maths: the "Done when" values ----------------------------------


def test_kelly_fraction():
    assert kmath.kelly_fraction(P) == pytest.approx(0.2)
    assert kmath.kelly_fraction(0.5, b=2) == pytest.approx(0.25)  # (2·0.5 − 0.5)/2
    assert kmath.kelly_fraction(0.4) == pytest.approx(-0.2)  # bet the other side
    with pytest.raises(ValueError):
        kmath.kelly_fraction(1.2)


@pytest.mark.parametrize("f,expected", [(0.1, 0.0150), (0.2, 0.0201), (0.4, -0.0025)])
def test_growth_rates_match_research_values(f, expected):
    # The research notes give these to 4 places; −0.0025 is −0.002447 rounded up.
    g = kmath.growth_rate(f, P)
    assert g == pytest.approx(expected, abs=6e-5)
    assert g == pytest.approx(P * math.log(1 + f) + (1 - P) * math.log(1 - f))


def test_growth_rate_shape():
    g_star = kmath.growth_rate(0.2, P)
    assert kmath.growth_rate(0.0, P) == 0
    assert kmath.growth_rate(1.0, P) == -math.inf
    assert kmath.growth_rate(0.19, P) < g_star and kmath.growth_rate(0.21, P) < g_star
    assert kmath.growth_rate(0.1, P) / g_star == pytest.approx(0.747, abs=0.001)  # half Kelly
    assert kmath.growth_rate(-0.2, 0.4) == pytest.approx(g_star)  # tails, mirrored coin
    assert kmath.growth_rate(1.0, 1.0) == pytest.approx(math.log(2))  # sure thing: all-in doubles


def test_zero_growth_fraction():
    root = kmath.zero_growth_fraction(P)
    assert root == pytest.approx(0.3894, abs=1e-4)
    assert kmath.growth_rate(root, P) == pytest.approx(0, abs=1e-12)
    assert kmath.zero_growth_fraction(0.5) == 0


def all_sequences(n):
    for seq in product((0, 1), repeat=n):
        k = sum(seq)
        yield k, P**k * (1 - P) ** (n - k)


def test_wealth_distribution_against_brute_force():
    n, f, w0 = 10, 0.3, 25.0
    seqs = list(all_sequences(n))
    mean = sum(prob * kmath.final_wealth(w0, f, k, n) for k, prob in seqs)
    assert kmath.mean_final_wealth(w0, f, P, n) == pytest.approx(mean)
    below = sum(prob for k, prob in seqs if kmath.final_wealth(w0, f, k, n) < w0)
    assert kmath.prob_below(1.0, f, P, n) == pytest.approx(below)
    wealths = sorted((kmath.final_wealth(w0, f, k, n), prob) for k, prob in seqs)
    cum, median = 0.0, None
    for wealth, prob in wealths:
        cum += prob
        if cum >= 0.5 and median is None:
            median = wealth
    assert kmath.median_final_wealth(w0, f, P, n) == pytest.approx(median)


def test_ruin_and_drawdown_formulas():
    assert kmath.gamblers_ruin(5, P) == pytest.approx((2 / 3) ** 5)
    assert kmath.gamblers_ruin(5, 0.5) == 1.0
    assert kmath.drawdown_approx(0.5, 1.0) == pytest.approx(0.5)  # full Kelly halves 50%
    assert kmath.drawdown_approx(0.5, 0.5) == pytest.approx(0.125)
    assert kmath.drawdown_approx(0.5, 2.0) == 1.0


def test_beta_posterior_and_sampler():
    assert kmath.posterior_mean(5, 5, 7, 3) == pytest.approx(12 / 20)
    rng = Rng(3)
    res = monte_carlo(lambda r: kmath.sample_beta(r, 5, 5), 20_000, rng)
    assert abs(res.mean - 0.5) < 4 * res.std_err
    assert res.variance == pytest.approx(25 / (100 * 11), rel=0.05)
    res = monte_carlo(lambda r: kmath.sample_beta(r, 2, 6), 20_000, rng)
    assert abs(res.mean - 0.25) < 4 * res.std_err
    with pytest.raises(ValueError):
        kmath.sample_beta(rng, 0, 2)


# --- simulation agrees with the exact values within standard error -------


def test_simulated_log_growth_matches_g():
    n = 100
    for f in (0.1, 0.2, 0.4):

        def trial(rng, f=f):
            path = sim.simulate_paths(rng, 1.0, f, P, n, 1)[0]
            return math.log(path[-1]) / n

        res = monte_carlo(trial, 2000, Rng(1))
        assert abs(res.mean - kmath.growth_rate(f, P)) < 4 * res.std_err


def test_simulated_probabilities_match_exact():
    n, runs = 100, 2000
    paths = sim.simulate_paths(Rng(2), 25.0, 0.3, P, n, runs)
    below = sim.proportion(sum(p[-1] < 25.0 for p in paths), runs)
    assert abs(below.value - kmath.prob_below(1.0, 0.3, P, n)) < 4 * below.std_err
    # Mean wealth at a small fraction (the mean is heavy-tailed for large f).
    res = monte_carlo(lambda r: sim.simulate_paths(r, 25.0, 0.1, P, 50, 1)[0][-1], 4000, Rng(4))
    assert abs(res.mean - kmath.mean_final_wealth(25.0, 0.1, P, 50)) < 4 * res.std_err


def test_fixed_bet_ruin_simulation():
    ruin = sim.fixed_bet_ruin(Rng(5), 2500, 500, P, 400, 1500)
    assert abs(ruin.value - kmath.gamblers_ruin(5, P)) < 4 * ruin.std_err + 0.01


def test_drawdown_frequency_and_quantile():
    paths = [[10.0, 4.0, 12.0], [10.0, 9.0, 8.0]]
    assert sim.drawdown_frequency(paths, 0.5).value == 0.5
    assert sim.quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert sim.short_money(3_220_637) == "$3.22M" and sim.short_money(12.5) == "$12.50"


def test_fan_chart_shape():
    paths = sim.simulate_paths(Rng(6), 25.0, 0.2, P, 80, 200)
    chart = sim.fan_chart(paths, width=40, height=10).splitlines()
    assert len(chart) == 10 + 3
    assert "start $25.00" in chart[0] + "".join(chart)
    assert all(len(line) == len(chart[0]) for line in chart[:10])
    assert "* median" in chart[-1]


# --- the game ----------------------------------------------------------------


def perfect_factory(module):
    def ask(q):
        return module.truth(module_state["s"], q), 1.0

    module_state = {}
    return ask, module_state


def play(config, ask_fn, seed=1):
    module = CoinFlip()
    states = []
    original = module.questions

    def questions(state):
        states.append(state)
        return original(state)

    module.questions = questions
    res = run_session(module, seed=seed, ask=lambda q: ask_fn(module, states[-1], q), config=config)
    return module, res, states


def perfect(module, state, q):
    return module.truth(state, q), 1.0


def test_perfect_player_tracks_kelly_exactly():
    module, res, _ = play({"flips": 60}, perfect)
    assert all(t.score.correct for t in res.turns)
    assert "you $" in res.summary
    final = res.result
    shadow = [line for line in res.summary.splitlines() if line.startswith("Same flips")][0]
    assert f"Kelly ${final:,.2f}" in shadow  # same bets on the same flips


def test_opening_questions_classic():
    _, res, _ = play({"flips": 30}, perfect)
    cats = [t.question.category for t in res.turns[:3]]
    assert cats == ["kelly-fraction", "kelly-risk", "kelly-bet"]
    assert res.turns[0].truth == pytest.approx(0.2)
    assert res.turns[1].truth == pytest.approx(kmath.prob_below(1.0, 0.3, P, 30))


def test_bets_settle_on_the_flip():
    bets = iter([5.0, -2.0, 0.0] * 10)

    def ask(module, state, q):
        if q.category != "kelly-bet":
            return 0.0, 1.0
        return next(bets), 1.0

    module, res, states = play({"flips": 3}, ask)
    final = states[-1]
    w = 25.0
    for i, bet in enumerate([5.0, -2.0]):
        s0, s1 = states[i], states[i + 1]
        heads = s1.heads - s0.heads
        w += bet if heads else -bet
        assert s1.wealth_c == round(w * 100)
    assert res.result == pytest.approx(final.wealth_c / 100)


def test_cap_stops_the_game_and_limits_kelly():
    module, res, states = play({"cap": 30, "flips": 300}, perfect, seed=2)
    last = states[-1]
    for s in states:
        assert module.kelly_bet_c(s) <= 3000 - s.wealth_c
    assert res.result == 30.0 or last.flip == 299
    assert "cap" in res.summary


def test_going_broke_ends_the_game():
    def all_in(module, state, q):
        return (state.wealth_c / 100 if q.category == "kelly-bet" else 0.0), 1.0

    for seed in range(20):  # find a seed where an early flip is tails
        _, res, states = play({"flips": 50}, all_in, seed=seed)
        if res.result == 0:
            assert "went broke" in res.summary and "bet everything" in res.summary
            assert states[-1].flip < 49
            return
    pytest.fail("no losing flip in 20 seeds")


def test_unknown_mode_estimates_and_bayes_kelly():
    module, res, states = play({"mode": "unknown", "flips": 35}, perfect, seed=7)
    est = [t for t in res.turns if t.question.category == "bias-estimate"]
    assert [t.question.id for t in est] == ["est10", "est20", "est30"]
    for t in est:
        assert t.score.correct and 0 < t.truth < 1
    shadow = [line for line in res.summary.splitlines() if line.startswith("Same flips")][0]
    assert f"Bayes-Kelly ${res.result:,.2f}" in shadow
    assert "oracle Kelly" in shadow and "bias was p" in res.summary


def test_seeded_replay():
    a = play({"mode": "unknown", "flips": 20}, perfect, seed=9)[1]
    b = play({"mode": "unknown", "flips": 20}, perfect, seed=9)[1]
    assert a.result == b.result and a.summary == b.summary


def test_bad_config():
    m = CoinFlip()
    for cfg in ({"mode": "x"}, {"flips": 0}, {"cap": 20}, {"p": 1.5}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_bet_question_parsing_and_display():
    m = CoinFlip()
    s = m.init(Rng(0), {})
    q = [x for x in m.questions(s) if x.category == "kelly-bet"][0]
    assert q.kind is Kind.POINT and q.tolerance == pytest.approx(1.25)
    assert parse_answer(q, "20%") == pytest.approx(5.0)
    assert parse_answer(q, "-20%") == pytest.approx(-5.0)
    assert parse_answer(q, "7.5") == 7.5
    for bad in ("26", "-25.01", "120%"):
        with pytest.raises(ParseError):
            parse_answer(q, bad)
    assert format_truth(q, -3.2) == "−$3.20"


def test_lab_command(capsys):
    assert main(["lab", "kelly", "-o", "flips=20", "-o", "runs=50"]) == 0
    out = capsys.readouterr().out
    assert "Kelly fraction f* = 2p − 1 = 0.2000" in out and "Fan chart" in out
    assert main(["lab", "kelly", "-o", "p=0.4"]) == 2


def test_cli_play_kelly(tmp_path, monkeypatch, capsys):
    answers = iter(["0.2", "0.5", "5", "20%", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["play", "kelly", "--seed", "1", "--db", str(tmp_path / "h.db")]) == 0
    out = capsys.readouterr().out
    assert "Same flips: Kelly" in out and "stopped early" in out
    main(["stats", "--db", str(tmp_path / "h.db")])
    assert "kelly-bet" in capsys.readouterr().out


def test_binomial_helper_consistency():
    assert sum(binomial_pmf(k, 30, P) for k in range(31)) == pytest.approx(1.0)
