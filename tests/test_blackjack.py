import math

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind
from edge_engine.loop import run_session
from edge_engine.modules.blackjack import Blackjack
from edge_engine.modules.blackjack import count as hilo
from edge_engine.modules.blackjack.cards import HILO, LABELS, Rules, Shoe, is_blackjack, total
from edge_engine.modules.blackjack.ev import (
    INFINITE,
    Situation,
    Solver,
    comp_at_true_count,
    dealer_blackjack_chance,
    dealer_outcomes,
)
from edge_engine.modules.blackjack.lab import computed_index, computed_insurance_index
from edge_engine.modules.blackjack.strategy import UPCARDS, table
from edge_engine.prob import monte_carlo
from edge_engine.rng import Rng
from edge_engine.terminal import parse_answer

# --- published basic strategy: 4-8 decks, DAS, late surrender ------------------
# Columns: dealer 2 3 4 5 6 7 8 9 10 A.

S17 = """
hard 5    H  H  H  H  H  H  H  H  H  H
hard 6    H  H  H  H  H  H  H  H  H  H
hard 7    H  H  H  H  H  H  H  H  H  H
hard 8    H  H  H  H  H  H  H  H  H  H
hard 9    H  D  D  D  D  H  H  H  H  H
hard 10   D  D  D  D  D  D  D  D  H  H
hard 11   D  D  D  D  D  D  D  D  D  H
hard 12   H  H  S  S  S  H  H  H  H  H
hard 13   S  S  S  S  S  H  H  H  H  H
hard 14   S  S  S  S  S  H  H  H  H  H
hard 15   S  S  S  S  S  H  H  H  Rh H
hard 16   S  S  S  S  S  H  H  Rh Rh Rh
hard 17   S  S  S  S  S  S  S  S  S  S
hard 18   S  S  S  S  S  S  S  S  S  S
hard 19   S  S  S  S  S  S  S  S  S  S
hard 20   S  S  S  S  S  S  S  S  S  S
soft A2   H  H  H  D  D  H  H  H  H  H
soft A3   H  H  H  D  D  H  H  H  H  H
soft A4   H  H  D  D  D  H  H  H  H  H
soft A5   H  H  D  D  D  H  H  H  H  H
soft A6   H  D  D  D  D  H  H  H  H  H
soft A7   S  Ds Ds Ds Ds S  S  H  H  H
soft A8   S  S  S  S  S  S  S  S  S  S
soft A9   S  S  S  S  S  S  S  S  S  S
pair 22   P  P  P  P  P  P  H  H  H  H
pair 33   P  P  P  P  P  P  H  H  H  H
pair 44   H  H  H  P  P  H  H  H  H  H
pair 55   D  D  D  D  D  D  D  D  H  H
pair 66   P  P  P  P  P  H  H  H  H  H
pair 77   P  P  P  P  P  P  H  H  H  H
pair 88   P  P  P  P  P  P  P  P  P  P
pair 99   P  P  P  P  P  S  P  P  S  S
pair TT   S  S  S  S  S  S  S  S  S  S
pair AA   P  P  P  P  P  P  P  P  P  P
"""

# H17 differs from S17 in six cells.
H17_CHANGES = {
    ("hard 11", 1): "D",
    ("hard 15", 1): "Rh",
    ("hard 17", 1): "Rs",
    ("soft A7", 2): "Ds",
    ("soft A8", 6): "Ds",
    ("pair 88", 1): "Rp",
}


def parse_chart(text):
    out = {}
    for line in text.strip().splitlines():
        parts = line.split()
        out[f"{parts[0]} {parts[1]}"] = dict(zip(UPCARDS, parts[2:], strict=True))
    return out


def test_basic_strategy_matches_published_chart_s17():
    assert table(Rules(), decks=6) == parse_chart(S17)


def test_basic_strategy_matches_published_chart_h17():
    expected = parse_chart(S17)
    for (row, up), code in H17_CHANGES.items():
        expected[row][up] = code
    assert table(Rules(h17=True), decks=6) == expected


def test_infinite_deck_differs_only_on_knife_edges():
    inf = table(Rules())
    pub = parse_chart(S17)
    diffs = {(r, u) for r in pub for u in UPCARDS if inf[r][u] != pub[r][u]}
    assert diffs == {("soft A2", 5), ("soft A4", 4)}


# --- the full deck counts to zero ---------------------------------------------


def test_hilo_is_balanced():
    assert sum(HILO[c] for c in LABELS) * 4 == 0
    for seed in range(20):
        shoe = Shoe(6, Rng(seed))
        cut = Rng(seed + 100).randint(0, 312)
        shoe.pos = cut
        seen = shoe.running_count()
        rest = sum(HILO[c] for c in shoe.cards[cut:])
        assert seen + rest == 0  # whatever has been seen, the rest cancels it


def test_count_drill_ends_at_zero():
    m = Blackjack()
    rcs = []

    def ask(q):
        t = m.truth(state["s"], q)
        if q.category == "count-drill":
            rcs.append(t)
        return t, 1.0

    state = {}
    orig = m.questions
    m.questions = lambda s: (state.__setitem__("s", s), orig(s))[1]
    res = run_session(m, seed=3, ask=ask, config={"mode": "drill"})
    assert rcs[-1] == 0 and len(rcs) == 13
    assert res.result == len(res.turns)


# --- dealer and solver -----------------------------------------------------------


def test_dealer_outcomes_sum_to_one_and_match_simulation():
    for up in UPCARDS:
        d = dealer_outcomes(up, INFINITE, False)
        assert sum(d.values()) == pytest.approx(1.0)
    # Simulate a dealer showing 6 from an infinite deck (S17).
    deck = "A23456789TTTT"

    def trial(rng):
        cards = ["6", deck[rng.randbelow(13)]]
        while True:
            t, soft = total(cards)
            if t >= 17:
                return float(t > 21)
            cards.append(deck[rng.randbelow(13)])

    res = monte_carlo(trial, 40_000, Rng(8))
    exact = dealer_outcomes(6, INFINITE, False, peek=False)[22]
    assert abs(res.mean - exact) < 4 * res.std_err


def test_h17_makes_dealer_hit_soft_17():
    s17 = dealer_outcomes(6, INFINITE, False)
    h17 = dealer_outcomes(6, INFINITE, True)
    assert h17[17] < s17[17] and h17[22] > s17[22]


def test_simple_evs():
    s = Solver(INFINITE, Rules())
    assert s.stand(21, 10) > 0.9
    assert s.stand(16, 10) == pytest.approx(s.stand(12, 10))  # 12-16 all lose unless dealer busts
    evs = s.evs(Situation(16, False, 10))
    assert evs["surrender"] == -0.5 and evs["hit"] > evs["stand"]
    assert "split" not in evs
    assert set(s.evs(Situation(16, False, 10, pair=8))) == {
        "hit",
        "stand",
        "double",
        "split",
        "surrender",
    }
    after_split = s.evs(Situation(11, False, 10, first=True, split_hand=True))
    assert "double" in after_split and "surrender" not in after_split
    no_das = Solver(INFINITE, Rules(das=False))
    assert "double" not in no_das.evs(Situation(11, False, 10, split_hand=True))


def test_edge_and_payout():
    r = Rules()
    edge = Solver(INFINITE, r).round_ev()
    assert -0.006 < edge < -0.003  # about half a percent to the house
    six_five = Solver(INFINITE, Rules(payout=1.2)).round_ev()
    p_bj = 2 * (1 / 13) * (4 / 13)
    not_dealer_bj = sum(
        INFINITE[u - 1] * (1 - dealer_blackjack_chance(u, INFINITE)) for u in range(1, 11)
    )
    assert edge - six_five == pytest.approx(0.3 * p_bj * not_dealer_bj)
    assert edge - six_five == pytest.approx(0.01353, abs=0.00001)  # 0.3 × 8/169 × (1 − 8/169)


def test_edge_rises_about_half_a_percent_per_true_count():
    r = Rules()
    edges = [Solver(comp_at_true_count(tc), r).round_ev() for tc in range(-2, 6)]
    assert all(b > a for a, b in zip(edges, edges[1:], strict=False))
    slope = (edges[-1] - edges[0]) / 7
    assert 0.004 < slope < 0.007


def test_true_count_composition():
    c0 = comp_at_true_count(0)
    assert c0 == pytest.approx(INFINITE)
    c4 = comp_at_true_count(4)
    assert c4[9] > INFINITE[9] and c4[4] < INFINITE[4]
    assert sum(c4) == pytest.approx(1.0)


# --- deviation indices against Schlesinger --------------------------------------


def test_insurance_index():
    assert computed_insurance_index() == pytest.approx(hilo.INSURANCE_INDEX, abs=0.5)


@pytest.mark.parametrize("dev", hilo.DEVIATIONS, ids=lambda d: d.name)
def test_deviation_indices_match_published(dev):
    rules = Rules() if dev.group == "Fab4" else Rules(surrender=False)
    idx = computed_index(dev, rules)
    assert idx is not None
    assert abs(idx - dev.index) <= 1.25


def test_bet_spread_and_true_count():
    assert [hilo.bet_units(tc) for tc in (-3, 0, 1.9, 2.0, 3.5, 4.2, 5.0, 9)] == [
        1,
        1,
        1,
        2,
        4,
        6,
        8,
        8,
    ]
    assert hilo.true_count(10, 130) == pytest.approx(4.0)
    with pytest.raises(ValueError):
        hilo.true_count(1, 0)


# --- rounds on a stacked shoe ------------------------------------------------------


def stacked(cards, **config):
    """A game whose shoe starts with these cards: player, up, player, hole, then draws."""
    m = Blackjack()
    s = m.init(Rng(0), {"hands": 2, **config})
    s.shoe.cards = list(cards) + list(s.shoe.cards)
    s.shoe.pos = 0
    s.seen, s.net, s.round_no = [], 0.0, 0
    m._start_round(s)
    return m, s


def act(m, s, action):
    s.pending = action
    m.apply(s, "next")


def test_player_blackjack_pays():
    for payout, win in (("3:2", 1.5), ("6:5", 1.2)):
        m, s = stacked("A9K7", payout=payout)
        assert s.net == pytest.approx(win) and s.round_no == 1


def test_dealer_blackjack_takes_one_bet():
    m, s = stacked("9K8A")
    assert s.net == -1 and s.round_no == 1


def test_insurance_pays_two_to_one():
    m, s = stacked("TA9K")
    assert s.stage == "insurance"
    act(m, s, "take")
    assert s.net == 0  # +1 on insurance, −1 on the hand
    m, s = stacked("TA97")
    act(m, s, "take")
    assert s.net == -0.5 and s.stage == "decide"


def test_double_and_dealer_bust():
    m, s = stacked("665T" + "T" + "9")
    act(m, s, "double")
    assert s.net == 2


def test_split_eights_then_double_after_split():
    m, s = stacked("8T87" + "3" + "T" + "T")  # split cards: 3 to hand 1, T to hand 2
    act(m, s, "split")
    assert [h.cards for h in s.hands] == [["8", "3"], ["8", "T"]]
    act(m, s, "double")  # 8,3 → draws T → 21
    act(m, s, "stand")  # 8,T = 18 against dealer 17
    assert s.net == 3


def test_split_aces_get_one_card_each():
    m, s = stacked("A6AT" + "9K" + "T")
    act(m, s, "split")
    assert s.net == 2  # A9 and AK (21, not a blackjack) both win when the dealer busts


def test_surrender():
    m, s = stacked("TT67")
    act(m, s, "surrender")
    assert s.net == -0.5


def test_dealer_hits_soft_17_under_h17():
    m, s = stacked("TA96" + "4", h17=True)  # dealer A6 = soft 17, insurance first
    act(m, s, "decline")
    act(m, s, "stand")  # 19; dealer hits soft 17 → A64 = 21
    assert s.net == -1
    m, s = stacked("TA96" + "4")
    act(m, s, "decline")
    act(m, s, "stand")  # S17: dealer stands on 17, player 19 wins
    assert s.net == 1


def test_hole_card_is_not_counted_until_shown():
    m, s = stacked("2T5K", mode="count")
    m.apply(s, "next")  # bet stage → deal
    assert m.running_count(s) == HILO["2"] + HILO["T"] + HILO["5"]
    assert sum(m.unseen_counts(s)) == s.shoe.remaining + 1


def test_bust_chance_truth():
    m, s = stacked("TT67")  # hard 16 vs 10, strategy mode asks the bust chance
    qs = m.questions(s)
    assert [q.category for q in qs] == ["bust-chance", "decision-hard"]
    bust = m.truth(s, qs[0])
    # Fresh 6-deck shoe minus T, 6, T: cards worth 6+ (6, 7, 8, 9, tens) out of 309.
    assert bust == pytest.approx((23 + 24 + 24 + 24 + 94) / 309)


def test_insurance_truth():
    m, s = stacked("TA97")
    q = m.questions(s)[0]
    t = m.truth(s, q)
    p = 95 / 309  # 96 tens minus the player's T, out of 312 minus three known cards
    assert t["decline"] == 0 and t["take"] == pytest.approx(0.5 * (3 * p - 1))


def test_bet_sets_the_stake():
    m, s = stacked("TT67", mode="count")
    bet_q = [q for q in m.questions(s) if q.category == "bet-spread"][0]
    from edge_engine.scoring import score_answer

    m.observe(s, bet_q, 4.0, score_answer(bet_q, 4.0, 1.0, 1.0), 1.0)
    m.apply(s, "next")
    assert s.hands[0].bet == 4


# --- full sessions ---------------------------------------------------------------


def perfect_session(mode, seed, hands):
    m = Blackjack()
    holder = {}
    orig = m.questions

    def questions(s):
        holder["s"] = s
        return orig(s)

    m.questions = questions

    def ask(q):
        t = m.truth(holder["s"], q)
        return (max(t, key=t.get) if q.kind is Kind.DECISION else t), 1.0

    return run_session(m, seed=seed, ask=ask, config={"mode": mode, "hands": hands})


@pytest.mark.parametrize("mode", ["strategy", "count"])
def test_perfect_player_loses_no_ev(mode):
    res = perfect_session(mode, seed=5, hands=150)
    assert res.completed
    assert all(t.score.correct is not False for t in res.turns)
    assert "EV lost 0.000" in res.summary


def always_hit(q):
    if q.kind is Kind.DECISION:
        return "hit" if "hit" in q.choices else "decline"
    return 0.5


def test_mistakes_are_reported():
    m = Blackjack()
    res = run_session(
        m,
        seed=1,
        ask=lambda q: (always_hit(q), 1.0),
        config={"hands": 30},
    )
    assert "Most expensive mistakes" in res.summary
    assert "per 100 hands" in res.summary


def test_bad_config():
    m = Blackjack()
    for cfg in ({"mode": "x"}, {"decks": 0}, {"hands": 0}, {"penetration": 0.99}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_decision_keys():
    m, s = stacked("TT67")
    q = m.questions(s)[1]
    assert parse_answer(q, "r") == "surrender"
    assert parse_answer(q, "s") == "stand"
    assert parse_answer(q, "d") == "double"
    assert is_blackjack(["A", "K"]) and not is_blackjack(["A", "5", "5"])


def test_lab_and_cli(tmp_path, monkeypatch, capsys):
    assert main(["lab", "blackjack"]) == 0
    out = capsys.readouterr().out
    assert "published +3" in out and "Player's edge" in out
    answers = iter(["s", "0.3", "s", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["play", "blackjack", "--seed", "1", "--db", str(tmp_path / "h.db")]) == 0
    assert "Blackjack" in capsys.readouterr().out
    assert math.isfinite(1.0)
