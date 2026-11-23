from fractions import Fraction
from itertools import combinations, product

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind
from edge_engine.loop import run_session
from edge_engine.modules.market import MarketMaking, bots, contract
from edge_engine.rng import Rng
from edge_engine.terminal import ParseError, parse_answer

DECK = [v for v in contract.CARD_VALUES for _ in range(4)]


def brute(kind, revealed, n):
    """Exact distribution of the sum by listing every outcome."""
    m = n - len(revealed)
    dist = {}
    if kind == "dice":
        outcomes = [(seq, Fraction(1, 6**m)) for seq in product(range(1, 7), repeat=m)]
    else:
        pool = list(DECK)
        for v in revealed:
            pool.remove(v)
        combos = list(combinations(range(len(pool)), m))
        outcomes = [(tuple(pool[i] for i in c), Fraction(1, len(combos))) for c in combos]
    for seq, p in outcomes:
        s = sum(revealed) + sum(seq)
        dist[s] = dist.get(s, Fraction(0)) + p
    return dist


def moments(dist):
    mean = sum(s * p for s, p in dist.items())
    return mean, sum((s - mean) ** 2 * p for s, p in dist.items())


@pytest.mark.parametrize(
    "kind,revealed,n",
    [
        ("dice", [], 3),
        ("dice", [6], 3),
        ("dice", [2, 5], 4),
        ("cards", [], 2),
        ("cards", [13], 3),
        ("cards", [1, 1, 7], 5),
    ],
)
def test_exact_statistics_against_brute_force(kind, revealed, n):
    dist = brute(kind, revealed, n)
    mean, var = moments(dist)
    assert contract.distribution(kind, revealed, n) == dist
    assert contract.fair_value(kind, revealed, n) == mean
    assert contract.variance(kind, revealed, n) == var


def test_research_note_values():
    assert contract.fair_value("dice", [], 3) == Fraction(21, 2)
    assert contract.variance("dice", [], 3) == Fraction(35, 4)  # 8.75
    assert contract.fair_value("cards", [], 1) == 7
    assert contract.variance("cards", [], 1) == 14
    v3 = contract.variance("cards", [], 3)
    assert v3 == Fraction(3 * 14 * 49, 51)  # without-replacement correction
    assert float(v3) == pytest.approx(40.35, abs=0.01)


def test_cards_three_variance_by_full_enumeration():
    sums = [sum(c) for c in combinations(DECK, 3)]  # 22,100 hands
    mean = Fraction(sum(sums), len(sums))
    var = Fraction(sum((s - mean) ** 2 for s in sums), len(sums))
    assert (mean, var) == (21, contract.variance("cards", [], 3))


def test_informed_value_is_the_conditional_mean():
    for kind, revealed, peek, n in (("dice", [3], 6, 3), ("cards", [12], 1, 3)):
        mean, _ = moments(brute(kind, revealed + [peek], n))
        assert contract.informed_value(kind, revealed, peek, n) == mean


def test_prob_at_least_and_errors():
    assert contract.prob_at_least("dice", [], 2, 12) == Fraction(1, 36)
    assert sum(contract.distribution("cards", [], 3).values()) == 1
    with pytest.raises(ValueError):
        contract.unseen_cards([5] * 5)
    with pytest.raises(ValueError):
        contract.fair_value("dice", [1, 2, 3], 2)


# --- bots -------------------------------------------------------------------------


def test_decide():
    bid, ask = Fraction(9), Fraction(11)
    assert bots.decide(12, bid, ask) == -1  # it buys: you sell
    assert bots.decide(8, bid, ask) == 1
    assert bots.decide(10, bid, ask) == 0
    assert bots.price(9.3) == Fraction(93, 10)


def test_noise_trade_rate_matches_theory():
    """At half-width sd/2, each noise trader trades with chance (sd − h)/sd = 1/2."""
    rng = Rng(1)
    items = [3, 4, 5, 6]
    fair = contract.fair_value("dice", [], 4)
    h = bots.price(contract.std_dev("dice", [], 4) / 2)
    trades, n = 0, 4000
    for _ in range(n // 4):
        trades += len(bots.run_round(rng, "dice", items, 0, fair - h, fair + h, 0, 4, 0.0, 99))
    p = trades / n
    assert abs(p - 0.5) < 4 * (0.25 / n) ** 0.5


def test_informed_traders_only_hit_mispriced_quotes():
    rng = Rng(2)
    items = [6, 1, 1, 1]  # the next die is a 6: worth 6 + 3 × 3.5 = 16.5, fair is 14
    fair = contract.fair_value("dice", [], 4)
    wide = bots.run_round(rng, "dice", items, 0, fair - 3, fair + 3, 0, 50, 1.0, 99)
    assert wide == []  # 16.5 is inside 11-17: an informed trader has nothing to gain
    narrow = bots.run_round(rng, "dice", items, 0, fair - 1, fair + 1, 0, 50, 1.0, 99)
    assert len(narrow) == 50  # 16.5 is above the 15 ask: every one of them buys
    for t in narrow:
        assert t.side == -1 and t.informed and t.value == Fraction(33, 2)
        assert t.side * (t.value - t.fair) < 0  # adverse selection costs you


def test_position_limit_is_respected():
    rng = Rng(3)
    items = [6, 6, 6, 6]
    fair = contract.fair_value("dice", [], 4)
    trades = bots.run_round(rng, "dice", items, 0, fair - 1, fair + 1, -3, 50, 1.0, 5)
    assert len(trades) == 2  # from −3 you can only sell 2 more before −5


# --- the P&L breakdown adds up exactly ----------------------------------------------


def random_quoter(module, holder, rng):
    def ask(q):
        s = holder["s"]
        t = module.truth(s, q)
        if q.kind is Kind.INTERVAL:
            w = q.params["max_width"]
            centre = t + rng.uniform(-1.5, 1.5)
            half = rng.uniform(0.2, w / 2)
            return (round(centre - half, 1), round(centre + half, 1)), 1.0
        return t, 1.0

    return ask


def play(seed, config, quoter=random_quoter):
    m = MarketMaking()
    holder = {}
    orig = m.questions

    def questions(s):
        holder["s"] = s
        return orig(s)

    m.questions = questions
    res = run_session(m, seed=seed, ask=quoter(m, holder, Rng(seed + 1000)), config=config)
    return m, holder["s"], res


@pytest.mark.parametrize("seed", range(25))
def test_breakdown_adds_up_exactly(seed):
    kind = "dice" if seed % 2 else "cards"
    m, s, res = play(seed, {"contract": kind, "informed": 0.4, "bots": 6})
    settle = Fraction(sum(s.items))
    b = bots.breakdown(s.trades, settle)
    assert b.parts_sum() == b.total  # exact Fractions, no tolerance
    assert b.total == s.cash + s.position * settle
    assert res.result == float(b.total)
    noise = bots.breakdown([t for t in s.trades if not t.informed], settle)
    smart = bots.breakdown([t for t in s.trades if t.informed], settle)
    assert noise.adverse == 0
    assert noise.total + smart.total == b.total


def test_full_round_against_mixed_flow():
    def fair_quoter(module, holder, rng):
        def ask(q):
            s = holder["s"]
            t = module.truth(s, q)
            if q.kind is Kind.INTERVAL:
                h = module.sd(s) / 2
                return (t - h, t + h), 1.0
            return t, 1.0

        return ask

    m, s, res = play(7, {"informed": 0.3}, fair_quoter)
    assert res.completed and s.shown == s.n == 4
    cats = [t.question.category for t in res.turns]
    assert cats[0] == "binary-option" and cats.count("quote") == 4
    assert all(t.score.correct for t in res.turns)
    assert "spread" in res.summary and "adverse selection" in res.summary
    assert "Settlement" in res.summary


def test_mark_to_market_question_appears_after_trades():
    m, s, res = play(4, {"bots": 8})
    marks = [t for t in res.turns if t.question.category == "mark-to-market"]
    assert marks and all(t.score.correct for t in marks)


def test_quote_parsing():
    m = MarketMaking()
    s = m.init(Rng(0), {})
    q = [x for x in m.questions(s) if x.category == "quote"][0]
    assert q.params["max_width"] == 7.0  # 2 sd of 4 dice = 6.83, rounded up to a half
    assert parse_answer(q, "12.5 15.5") == (12.5, 15.5)
    assert parse_answer(q, "12.5@15.5") == (12.5, 15.5)
    for bad in ("10 18", "14 14", "15 13"):
        with pytest.raises(ParseError):
            parse_answer(q, bad)


def test_bad_config():
    m = MarketMaking()
    for cfg in ({"contract": "fx"}, {"n": 0}, {"informed": 1.5}, {"bots": 0}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_lab_and_cli(tmp_path, monkeypatch, capsys):
    assert main(["lab", "market", "-o", "games=5"]) == 0
    out = capsys.readouterr().out
    assert "52.706" in out and "best half-width" in out  # 4 cards: 4·14·48/51
    answers = iter(["0.3", "14", "3.4", "12.5 15.5", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["play", "market", "--seed", "1", "--db", str(tmp_path / "h.db")]) == 0
    assert "Your market" in capsys.readouterr().out
