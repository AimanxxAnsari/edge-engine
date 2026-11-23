from itertools import permutations

import numpy as np
import pytest

from edge_engine.cli import main
from edge_engine.core import Kind
from edge_engine.loop import run_session
from edge_engine.modules.backgammon import Backgammon, bearoff, bots, shots
from edge_engine.modules.backgammon.board import (
    ROLLS,
    Position,
    legal_plays,
    result,
    start,
)
from edge_engine.modules.backgammon.lab import PUBLISHED_SHOTS, opening_counts
from edge_engine.modules.backgammon.td import Network, features, train
from edge_engine.prob import monte_carlo
from edge_engine.rng import Rng

# --- a second, deliberately simple move generator ----------------------------------
# It keeps a plain list of the mover's checker locations (25 = bar, 0 = off) and a
# dict of opponent counts, tries every order of the dice, and applies the "use as
# many dice as possible" and "larger die" rules over the finished sequences.


def ref_key(mine, opp, opp_bar, opp_off):
    pts = [0] * 24
    for c in mine:
        if 1 <= c <= 24:
            pts[c - 1] += 1
    for p, n in opp.items():
        pts[p - 1] -= n
    return (tuple(pts), mine.count(25), opp_bar, mine.count(0), opp_off)


def ref_steps(mine, opp, opp_bar, die):
    out = []
    if 25 in mine:
        sources = [25]
    else:
        sources = sorted(set(c for c in mine if c != 0))
    all_home = all(c <= 6 for c in mine)
    for src in sources:
        dst = (25 - die) if src == 25 else src - die
        if dst >= 1:
            if opp.get(dst, 0) >= 2:
                continue
            new_opp, new_bar = dict(opp), opp_bar
            if new_opp.get(dst, 0) == 1:
                del new_opp[dst]
                new_bar += 1
            new_mine = list(mine)
            new_mine.remove(src)
            new_mine.append(dst)
            out.append((new_mine, new_opp, new_bar))
        else:
            if not all_home or src == 25:
                continue
            exact = dst == 0
            highest = max(c for c in mine if c != 0)
            if exact or src == highest:
                new_mine = list(mine)
                new_mine.remove(src)
                new_mine.append(0)
                out.append((new_mine, dict(opp), opp_bar))
    return out


def ref_plays(pos: Position, roll):
    mine = [25] * pos.bar + [0] * pos.off
    opp = {}
    for i, n in enumerate(pos.points):
        if n > 0:
            mine += [i + 1] * n
        elif n < 0:
            opp[i + 1] = -n
    a, b = roll
    orders = {(a,) * 4} if a == b else set(permutations((a, b)))
    finished = []  # (dice used, first die, key)

    def go(state, dice, used, first):
        m, o, ob = state
        nxt = ref_steps(m, o, ob, dice[0]) if dice else []
        if not nxt:
            finished.append((used, first, ref_key(m, o, ob, pos.opp_off)))
            return
        for st in nxt:
            go(st, dice[1:], used + 1, first if first else dice[0])

    for order in orders:
        go((mine, opp, pos.opp_bar), list(order), 0, 0)
    most = max(u for u, _, _ in finished)
    keep = [(u, f, k) for u, f, k in finished if u == most]
    if most == 1 and a != b and any(f == max(a, b) for _, f, _ in keep):
        keep = [x for x in keep if x[1] == max(a, b)]
    return {k for _, _, k in keep}


def random_positions(n, seed):
    rng = Rng(seed)
    out = []
    while len(out) < n:
        pos = start()
        for _ in range(rng.randint(1, 60)):
            roll = (rng.randint(1, 6), rng.randint(1, 6))
            play = bots.random_bot(rng)(pos, roll)
            after = play.after if play else pos
            if result(after):
                break
            pos = after.flip()
            out.append(pos)
    return out[:n]


def test_move_generator_agrees_with_reference_everywhere():
    positions = random_positions(250, seed=1)
    checked = 0
    for pos in positions:
        assert pos.is_valid()
        for roll in ROLLS:
            fast = {p.after.key() for p in legal_plays(pos, roll)}
            assert fast == ref_plays(pos, roll), (pos, roll)
            checked += 1
    assert checked == 250 * 21


def test_opening_counts():
    counts = opening_counts()
    for roll in ROLLS:
        assert counts[roll] == len(ref_plays(start(), roll))
    assert counts[(1, 3)] == 16 and sum(counts.values()) == 447


def pos_from(mine: dict, opp: dict, bar=0, opp_bar=0, off=None, opp_off=None):
    pts = [0] * 24
    for p, n in mine.items():
        pts[p - 1] = n
    for p, n in opp.items():
        pts[p - 1] = -n
    mine_n = sum(mine.values()) + bar
    opp_n = sum(opp.values()) + opp_bar
    return Position(
        tuple(pts),
        bar,
        opp_bar,
        15 - mine_n if off is None else off,
        15 - opp_n if opp_off is None else opp_off,
    )


def test_closed_board_means_no_entry():
    pos = pos_from({24: 1}, {p: 2 for p in range(19, 25) if p != 24} | {24: 0} | {19: 2}, bar=1)
    closed = pos_from({1: 1}, {p: 2 for p in range(19, 25)}, bar=1)
    for roll in ROLLS:
        assert legal_plays(closed, roll)[0].moves == ()
    assert pos.bar == 1


def test_larger_die_rule():
    # One checker on 24; the 18 is blocked, so 6 then 5 is impossible, and 5 then 6
    # lands on the blocked 13. Either die alone can be played: it must be the 6? No:
    # the 6 is blocked from 24, so only the 5 can be played.
    pos = pos_from({24: 1}, {18: 2, 13: 2})
    plays = legal_plays(pos, (6, 5))
    assert [str(p) for p in plays] == ["24/19"]
    # Now both single dice work but not both together: the larger die must be used.
    pos = pos_from({24: 1}, {13: 2, 12: 2})
    plays = legal_plays(pos, (6, 5))
    assert {str(p) for p in plays} == {"24/18"}


def test_bear_off_rules():
    pos = pos_from({2: 1, 1: 1}, {24: 2})
    assert {str(p) for p in legal_plays(pos, (6, 5))} == {"2/off 1/off"}
    pos = pos_from({5: 1, 3: 1}, {24: 2})
    # 6 first bears off the 5 (the highest checker); 1 first moves 5/4, then the 6
    # bears off from 4, now the highest. Two different results.
    assert {str(p) for p in legal_plays(pos, (6, 1))} == {"5/off 3/2", "5/4 4/off"}
    pos = pos_from({7: 1, 3: 1}, {24: 2})  # the 7 is outside, so no bearing off yet
    plays = legal_plays(pos, (6, 2))
    # 7/1 then the 2 can't bear off from 1 (3 is higher): 3/1. Or 7/5, then the 6
    # bears off the 5, now the highest checker.
    assert sorted(str(p) for p in plays) == ["7/1 3/1", "7/5 5/off"]


def test_must_use_both_dice_when_possible():
    # 9/3 is blocked, so the 6 can't go first; 9/8 then 8/2 uses both dice, so playing
    # the 1 alone (9/8) is not allowed.
    pos = pos_from({9: 1}, {3: 2})
    plays = legal_plays(pos, (6, 1))
    assert [str(p) for p in plays] == ["9/8 8/2"]


def test_flip_pips_and_results():
    s = start()
    assert s.pips() == s.opp_pips() == 167 and s.flip() == s and s.flip().flip() == s
    single = pos_from({}, {24: 1}, off=15, opp_off=14)
    gammon = pos_from({}, {24: 1}, off=15, opp_off=0)
    backgammon = pos_from({}, {3: 1}, off=15, opp_off=0)
    assert (result(single), result(gammon), result(backgammon)) == (1, 2, 3)
    assert result(s) == 0


# --- shots ------------------------------------------------------------------------------


def test_shot_table_is_reproduced():
    table = shots.open_board_table()
    assert [table[d] for d in range(1, 13)] == list(PUBLISHED_SHOTS)


def test_blocks_cut_shots():
    # Blot on 13, hitter 8 pips away on 5: 6-2, 5-3, 4-4, 2-2 hit on an open board (6 rolls).
    open_board = pos_from({13: 1}, {5: 1}, off=14, opp_off=14)
    assert shots.shots(open_board, 13) == 6
    # Our points on 11 and 9: 4-4 (5-9-13) and 2-2 (5-7-9-11-13) are blocked; 6-2 still
    # hits by playing the 2 first (5-7-13), and 5-3 is untouched. 4 rolls left.
    blocked = pos_from({13: 1, 11: 2, 9: 2}, {5: 1}, off=10, opp_off=14)
    assert shots.shots(blocked, 13) == 4
    assert set(shots.hitting_rolls(blocked, 13)) == {(2, 6), (3, 5)}


def test_bar_checker_shoots():
    pos = pos_from({3: 1}, {}, opp_bar=1, off=14, opp_off=14)
    assert shots.shots(pos, 3) == 14  # any 3 (11), 1-2 and 2-1 (2), and 1-1 (1)


# --- bots --------------------------------------------------------------------------------


def test_heuristic_bot_beats_random():
    rng = Rng(3)
    wins = 0
    for g in range(40):
        if g % 2 == 0:
            winner, _ = bots.play_game(bots.greedy_bot, bots.random_bot(rng), rng)
            wins += winner == 0
        else:
            winner, _ = bots.play_game(bots.random_bot(rng), bots.greedy_bot, rng)
            wins += winner == 1
    assert wins >= 30


def test_evaluation_prefers_making_points():
    pos = start()
    plays = legal_plays(pos, (3, 1))
    best = max(plays, key=lambda p: bots.evaluate(p.after))
    assert str(best) in ("8/5 6/5", "6/5 8/5")  # the classic: make the 5-point


# --- bear-off and the cube ---------------------------------------------------------------


def test_bearoff_exact_cases():
    assert bearoff.expected_rolls((0, 0, 0, 0, 0, 1)) == pytest.approx(1 + 9 / 36)
    assert bearoff.expected_rolls((1, 1, 0, 0, 0, 0)) == pytest.approx(1.0)
    dist = bearoff.finish_distribution((0, 0, 0, 0, 0, 2))
    assert dist[1] == pytest.approx(4 / 36)  # only 3-3, 4-4, 5-5, 6-6 finish at once
    assert sum(dist) == pytest.approx(1.0)


def test_bearoff_win_chance_against_simulation():
    a, b = (0, 1, 2, 0, 1, 0), (1, 0, 1, 1, 0, 1)
    exact = bearoff.win_chance(a, b)

    def policy(home, roll):
        best = min(
            legal_plays(bearoff._home_position(home), roll),
            key=lambda p: bearoff.expected_rolls(tuple(p.after.points[:6])),
        )
        return tuple(best.after.points[:6])

    def trial(rng):
        homes = [a, b]
        turn = 0
        while True:
            roll = (rng.randint(1, 6), rng.randint(1, 6))
            homes[turn] = policy(homes[turn], roll)
            if sum(homes[turn]) == 0:
                return float(turn == 0)
            turn = 1 - turn

    res = monte_carlo(trial, 3000, Rng(5))
    assert abs(res.mean - exact) < 4 * res.std_err


def test_cube_maths():
    assert bearoff.take_values(0.75) == {"take": -1.0, "drop": -1.0}  # the take point
    for p in (0.3, 0.5, 0.55, 0.8, 0.95):
        v = bearoff.cube_values(p)
        assert (v["double"] > v["no double"]) == (p > 0.5)  # dead cube: double when favourite
    assert bearoff.cube_values(0.9)["double"] == 1.0  # they drop
    r = bearoff.race_rule(100, 107)
    assert not r["double"] and r["take"]
    r = bearoff.race_rule(100, 110)
    assert r["double"] and r["redouble"] and r["take"]
    assert not bearoff.race_rule(100, 113)["take"]


# --- TD network ---------------------------------------------------------------------------


def test_td_gradient_matches_finite_differences():
    net = Network(hidden=8, seed=2)
    x = features(start())
    _, g = net.gradient(x)
    eps = 1e-6
    for name, idx in (("w2", 3), ("b1", 5), ("w1", (2, 10)), ("w1", (7, 192))):
        param = getattr(net, name)
        old = param[idx]
        param[idx] = old + eps
        up = net.gradient(x)[0]
        param[idx] = old - eps
        down = net.gradient(x)[0]
        param[idx] = old
        assert g[name][idx] == pytest.approx((up - down) / (2 * eps), rel=1e-4, abs=1e-9)


def test_td_update_moves_towards_target():
    net = Network(hidden=8, seed=3)
    x = features(start())
    before = net.gradient(x)[0]
    net.update(x, 1.0, alpha=0.5)
    assert net.gradient(x)[0] > before
    assert features(start()).shape == (196,)
    assert np.isclose(features(start())[:4].sum(), 0.0)  # mover has nothing on point 1


@pytest.mark.slow
def test_td_learns_to_beat_random():
    net = Network(seed=1)
    train(net, 1000, Rng(1))
    rng = Rng(7)
    wins = 0
    for g in range(40):
        if g % 2 == 0:
            winner, _ = bots.play_game(net.choose, bots.random_bot(rng), rng)
            wins += winner == 0
        else:
            winner, _ = bots.play_game(bots.random_bot(rng), net.choose, rng)
            wins += winner == 1
    assert wins >= 32


# --- the game -----------------------------------------------------------------------------


def perfect(config, seed=1):
    m = Backgammon()
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


@pytest.mark.parametrize("mode", ["shots", "cube"])
def test_spot_modes(mode):
    res = perfect({"mode": mode, "spots": 6})
    assert res.completed and all(t.score.correct is not False for t in res.turns)


def test_full_game_against_the_bot():
    res = perfect({"mode": "play", "bot": "random"}, seed=2)
    assert res.completed
    cats = {t.question.category for t in res.turns}
    assert "checker-play" in cats and "shots" in cats
    assert res.result in (-3, -2, -1, 1, 2, 3)
    assert "Games: 1" in res.summary


def test_bad_config():
    m = Backgammon()
    for cfg in ({"mode": "chouette"}, {"bot": "gnubg"}, {"games": 0}):
        with pytest.raises(ValueError):
            m.init(Rng(0), cfg)


def test_lab_and_cli(tmp_path, monkeypatch, capsys):
    assert main(["lab", "backgammon", "-o", "games=4"]) == 0
    out = capsys.readouterr().out
    assert "computed  11  12  14" in out and "total over the 21 rolls: 447" in out
    answers = iter(["167", "1", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["play", "backgammon", "--seed", "1", "--db", str(tmp_path / "h.db")]) == 0
    assert "Pip count" in capsys.readouterr().out
