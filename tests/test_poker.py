from collections import Counter
from fractions import Fraction
from itertools import combinations, product

import numpy as np
import pytest

from edge_engine.cli import main
from edge_engine.core import Kind, Question
from edge_engine.loop import run_session
from edge_engine.modules.poker import Poker
from edge_engine.modules.poker import equity as eq
from edge_engine.modules.poker.cfr import CFRPlus, Tree
from edge_engine.modules.poker.evaluator import CATEGORIES, card, cards, category, evaluate
from edge_engine.modules.poker.games import Kuhn, Leduc
from edge_engine.modules.poker.lab import SEVEN_CARD_COUNTS, SEVEN_CARD_TOTAL
from edge_engine.modules.poker.module import bot_and_best_response, solved
from edge_engine.rng import Rng
from edge_engine.scoring import score_answer


@pytest.fixture(scope="module")
def kuhn():
    tree = Tree(Kuhn())
    return tree, CFRPlus(tree).solve(2000)


@pytest.fixture(scope="module")
def leduc():
    tree = Tree(Leduc())
    solver = CFRPlus(tree)
    checkpoints = []
    for n in (50, 200, 1500):
        solver.iterate(n - solver.iterations)
        checkpoints.append(tree.exploitability(solver.average()))
    return tree, solver.average(), checkpoints


# --- Kuhn: the "Done when" value and Kuhn's equilibrium family -----------------------


def test_kuhn_tree_shape(kuhn):
    tree, _ = kuhn
    assert len(tree.nodes) == 9 and len(tree.infosets) == 12 and len(tree.deals) == 6


def test_kuhn_reaches_game_value(kuhn):
    tree, avg = kuhn
    assert tree.value(avg) == pytest.approx(-1 / 18, abs=5e-4)
    assert tree.exploitability(avg) < 2e-4


def test_kuhn_strategy_is_in_the_equilibrium_family(kuhn):
    tree, avg = kuhn
    bet = {key: avg[i, 1] for i, key in enumerate(tree.infosets)}
    alpha = bet["J:"]
    assert 0 <= alpha <= 1 / 3 + 0.01
    assert bet["K:"] == pytest.approx(3 * alpha, abs=0.02)
    assert bet["Q:"] == pytest.approx(0, abs=0.01)
    assert bet["Q:pb"] == pytest.approx(alpha + 1 / 3, abs=0.02)
    assert bet["J:pb"] == pytest.approx(0, abs=0.01) and bet["K:pb"] == pytest.approx(1, abs=0.01)
    assert bet["J:p"] == pytest.approx(1 / 3, abs=0.02)  # second player bluffs a J
    assert bet["Q:b"] == pytest.approx(1 / 3, abs=0.02)  # and calls with a Q
    assert bet["K:p"] == pytest.approx(1, abs=0.01) and bet["J:b"] == pytest.approx(0, abs=0.01)


def pure_strategies(tree, player):
    mine = [i for i, p in enumerate(tree.infoset_player) if p == player]
    for choice in product(range(2), repeat=len(mine)):
        yield mine, choice


def test_best_response_matches_brute_force(kuhn):
    """Try all 64 pure strategies of the responder against a fixed opponent."""
    tree, avg = kuhn
    for opponent in (tree.uniform(), avg):
        for player in (0, 1):
            best = -np.inf
            for mine, choice in pure_strategies(tree, player):
                s = opponent.copy()
                for i, k in zip(mine, choice, strict=True):
                    s[i] = 0
                    s[i, k] = 1
                v = tree.value(s) * (1 if player == 0 else -1)
                best = max(best, v)
            br, _ = tree.best_response(opponent, player)
            assert br == pytest.approx(best)


def test_uniform_is_exploitable(kuhn):
    tree, _ = kuhn
    assert tree.exploitability(tree.uniform()) > 0.1


# --- Leduc --------------------------------------------------------------------------


def test_leduc_rules():
    g = Leduc()
    deals = g.deals()
    assert len(deals) == 24 and sum(w for _, w in deals) == pytest.approx(1)
    assert g.actions("") == ["c", "r"]
    assert g.actions("cr") == ["f", "c", "r"]
    assert g.actions("crr") == ["f", "c"]  # a bet and a raise per round
    assert g.child("cc", "r") == "cc/r"  # round 2 starts after check-check
    assert g.player("crc") == 0 and g.player("crc/c") == 1
    assert g.contributions("rrc/rc") == [1 + 4 + 4, 1 + 4 + 4]  # 2+2 raise, then a 4 bet
    assert g.payoff("rrc/rf", (0, 1, 2)) == 5  # player 1 folds after paying 5
    assert g.payoff("cc/cc", (0, 1, 0)) == 1  # J pairs the board and beats Q
    assert g.payoff("cc/cc", (1, 1, 2)) == 0  # equal ranks split


def test_leduc_converges(leduc):
    tree, avg, checkpoints = leduc
    assert len(tree.infosets) == 288
    assert checkpoints[0] > checkpoints[1] > checkpoints[2]
    assert checkpoints[-1] < 5e-4
    assert tree.value(avg) == pytest.approx(-0.0856, abs=1e-3)  # published game value


# --- hand evaluator -------------------------------------------------------------------


def score(text):
    return evaluate(cards(text))


def test_evaluator_order():
    hands = [
        "2c 3d 4h 5s 7c",  # high card
        "2c 2d 4h 5s 7c",  # pair
        "2c 2d 4h 4s 7c",  # two pair
        "2c 2d 2h 5s 7c",  # trips
        "Ac 2d 3h 4s 5c",  # wheel straight
        "2c 3d 4h 5s 6c",  # six-high straight beats the wheel
        "2c 4c 6c 8c Tc",  # flush
        "2c 2d 2h 5s 5c",  # full house
        "2c 2d 2h 2s 5c",  # quads
        "Ac 2c 3c 4c 5c",  # steel wheel
        "Tc Jc Qc Kc Ac",  # royal flush
    ]
    scores = [score(h) for h in hands]
    assert scores == sorted(scores) and len(set(scores)) == len(scores)
    assert CATEGORIES[category(score("Ac 2c 3c 4c 5c"))] == "straight flush"


def test_kickers_and_ties():
    assert score("Ac Ad 9h 5s 3c") > score("As Ah 9d 5c 2c")
    assert score("Kc Kd Qh Qs 2c") > score("Kh Ks Jh Js Ac")
    assert score("Ac Kd Qh Js 9c") == score("Ad Kh Qs Jc 9d")
    # Two sets of trips: the higher is the trips, the lower serves as the pair (333 22).
    assert score("2c 2d 2h 3s 3c 3d Ac") == score("3c 3d 3h 2s 2c Kc Qd")
    assert score("3c 3d 3h 2s 2c Ac Ad") > score("2c 2d 2h 3s 3c 3d Ac")  # 333 AA beats 333 22


def test_seven_cards_equal_best_five_card_subset():
    rng = Rng(11)
    for _ in range(3000):
        hand = rng.sample(range(52), 7)
        assert evaluate(hand) == max(evaluate(c) for c in combinations(hand, 5))


def test_seven_card_frequencies_match_known_counts():
    rng = Rng(12)
    n = 40_000
    counts = Counter(category(evaluate(rng.sample(range(52), 7))) for _ in range(n))
    chi2 = sum(
        (counts[c] - n * SEVEN_CARD_COUNTS[c] / SEVEN_CARD_TOTAL) ** 2
        / (n * SEVEN_CARD_COUNTS[c] / SEVEN_CARD_TOTAL)
        for c in range(9)
    )
    assert chi2 < 26.1  # 99.9th percentile, 8 degrees of freedom
    assert sum(SEVEN_CARD_COUNTS) == SEVEN_CARD_TOTAL


@pytest.mark.slow
def test_all_five_card_hands_give_the_known_counts():
    counts = Counter(category(evaluate(h)) for h in combinations(range(52), 5))
    assert [counts[c] for c in range(9)] == [
        1_302_540,
        1_098_240,
        123_552,
        54_912,
        10_200,
        5_108,
        3_744,
        624,
        40,
    ]


def test_card_parsing():
    assert card("As") == 51 and card("2c") == 0
    with pytest.raises(ValueError):
        card("1x")


# --- equity -----------------------------------------------------------------------------

SPOTS = [
    ("Ah Kh", "Qs Qd", "2h 7h Jc"),
    ("8s 9s", "Ac Ad", "6s 7d 2s"),
    ("Jc Td", "As Kc", "Qh 9h 3c"),
    ("Ks Jd", "Kd Td", "Ah 8h Th 2c"),
]


@pytest.mark.parametrize("hero,villain,board", SPOTS)
def test_monte_carlo_agrees_with_exact_enumeration(hero, villain, board):
    h, v, b = cards(hero), cards(villain), cards(board)
    exact = eq.exact(h, v, b)
    mc = eq.monte_carlo_equity(Rng(3), h, v, b, 3000)
    assert abs(mc.mean - float(exact.equity)) < 4 * mc.std_err
    other = eq.exact(v, h, b)
    assert exact.equity + other.equity == 1  # the two shares make the whole pot
    assert exact.win == other.lose and exact.tie == other.tie


def test_outs_and_one_card_equity():
    h, v, b = cards("Ks Jd"), cards("Kd Td"), cards("Ah 8h Th 2c")
    o = eq.outs(h, v, b)
    assert sorted(o) == sorted(cards("Jc Jh Js Qc Qd Qh Qs"))
    e = eq.exact(h, v, b)
    ties = e.tie * 44
    assert e.win == Fraction(len(o), 44) and ties == 0  # one card to come: equity = outs/unseen


def test_flush_draw_numbers_from_the_notes():
    assert 9 / 46 == pytest.approx(0.196, abs=0.001)
    assert eq.two_card_chance(9, 47) == pytest.approx(0.350, abs=0.001)


def test_preflop_aces_against_kings():
    r = eq.monte_carlo_equity(Rng(4), cards("As Ah"), cards("Ks Kh"), [], 4000)
    assert abs(r.mean - 0.82) < 0.025  # aces win about 82%


def test_equity_errors():
    with pytest.raises(ValueError):
        eq.exact(cards("As Ah"), cards("As Kh"), [])


# --- the game ----------------------------------------------------------------------------


def perfect_session(config, seed=1):
    m = Poker()
    holder = {}
    orig = m.questions

    def questions(s):
        holder["s"] = s
        return orig(s)

    m.questions = questions

    def ask(q):
        t = m.truth(holder["s"], q)
        return (max(t, key=t.get) if q.kind is Kind.DECISION else t), 1.0

    return run_session(m, seed=seed, ask=ask, config=config)


@pytest.mark.parametrize("mode", ["kuhn", "leduc", "spots"])
def test_perfect_player(mode):
    res = perfect_session({"mode": mode, "hands": 15})
    assert res.completed
    assert all(t.score.correct is not False for t in res.turns)


@pytest.mark.parametrize("bot", ["station", "maniac"])
def test_exploiting_a_bot_earns_its_best_response_value(bot):
    """Playing the best response for many hands earns the computed BR value."""
    hands = 600
    res = perfect_session({"mode": "kuhn", "bot": bot, "hands": hands}, seed=9)
    br = sum(bot_and_best_response("kuhn", bot, h)[2] for h in (0, 1)) / 2
    assert br > 0.1  # both bots are very exploitable
    per_hand = res.result / hands
    assert abs(per_hand - br) < 0.15


def test_best_play_depends_on_the_bot():
    tree, _ = solved("kuhn")
    j_first = tree.infoset_index["J:"]
    _, q_station, _ = bot_and_best_response("kuhn", "station", 0)
    assert q_station[j_first, 0] > q_station[j_first, 1]  # never bluff a calling station
    q_facing = tree.infoset_index["Q:pb"]
    _, q_maniac, _ = bot_and_best_response("kuhn", "maniac", 0)
    assert q_maniac[q_facing, 1] > q_maniac[q_facing, 0]  # call a maniac's bet with a Q


def test_decision_ties_count_as_right():
    q = Question(
        id="x",
        kind=Kind.DECISION,
        prompt="?",
        category="c",
        choices=("check", "bet"),
        tolerance=0.005,
    )
    assert score_answer(q, "bet", {"check": -1.0, "bet": -1.0004}, 1.0).correct
    assert not score_answer(q, "bet", {"check": -1.0, "bet": -1.01}, 1.0).correct


def test_bad_config():
    m = Poker()
    for cfg in ({"mode": "omaha"}, {"bot": "shark"}, {"hands": 0}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_lab_and_cli(tmp_path, monkeypatch, capsys):
    assert main(["lab", "poker", "-o", "samples=500"]) == 0
    out = capsys.readouterr().out
    assert "−1/18" in out and "288 information sets" in out
    answers = iter(["b", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["play", "poker", "--seed", "1", "--db", str(tmp_path / "h.db")]) == 0
    assert "Kuhn hand 1" in capsys.readouterr().out
