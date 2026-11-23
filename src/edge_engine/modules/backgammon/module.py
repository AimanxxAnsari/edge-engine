"""Backgammon: play against a bot, shot counting, and the doubling cube."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from . import bearoff, bots, shots
from .board import Play, Position, legal_plays, render, result, start

MODES = ("play", "shots", "cube")
BOTS = ("greedy", "1ply", "random", "td")
TIE = 0.02  # engine points: plays this close count as equally good


@dataclass
class Spot:
    kind: str  # 'shots', 'bearoff', 'race'
    pos: Position | None = None
    blot: int = 0
    mine: tuple[int, ...] = ()
    theirs: tuple[int, ...] = ()
    leader: int = 0
    trailer: int = 0


@dataclass
class BGState:
    mode: str
    rounds: int
    bot: str
    pos: Position = field(default_factory=start)  # hero's side when hero is to move
    roll: tuple[int, int] = (0, 0)
    plays: list[Play] = field(default_factory=list)
    stage: str = "move"  # move | shot | spot | done
    turn_no: int = 0
    round_no: int = 0
    net: int = 0
    pending: str | None = None
    log: list[str] = field(default_factory=list)
    spot: Spot | None = None
    decisions: int = 0
    best: int = 0
    lost: float = 0.0
    mistakes: list[tuple[float, str]] = field(default_factory=list)
    right: int = 0
    asked: int = 0


class Backgammon(GameModule):
    name = "backgammon"
    title = "Backgammon"

    def init(self, rng: Rng, config: Mapping[str, Any]) -> BGState:
        mode = str(config.get("mode", "play"))
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
        bot = str(config.get("bot", "greedy"))
        if bot not in BOTS:
            raise ValueError(f"unknown bot {bot!r}; choose from {', '.join(BOTS)}")
        rounds = int(config.get("games" if mode == "play" else "spots", 1 if mode == "play" else 8))
        if rounds < 1:
            raise ValueError("need at least one game or spot")
        self.rng = rng
        self.bot = self._make_bot(bot)
        s = BGState(mode=mode, rounds=rounds, bot=bot)
        if mode == "play":
            self._new_game(s)
        else:
            s.stage = "spot"
            s.spot = self._new_spot(s)
        return s

    def _make_bot(self, name: str):
        if name == "greedy":
            return bots.greedy_bot
        if name == "1ply":
            return bots.one_ply_bot
        if name == "random":
            return bots.random_bot(self.rng)
        from .td import DEFAULT_PATH, Network

        if not DEFAULT_PATH.exists():
            raise ValueError(
                "no trained network yet: run `edge-engine lab backgammon -o train=1500`"
            )
        return Network.load().choose

    # --- play -------------------------------------------------------------------------

    def _new_game(self, s: BGState) -> None:
        s.pos = start()
        s.turn_no = 0
        s.log.append(f"Game {s.round_no + 1}: you are X and move first, from 24 towards 1.")
        self._hero_roll(s)

    def _hero_roll(self, s: BGState) -> None:
        """Roll for the hero; pass automatically when no move is possible."""
        while True:
            s.roll = (self.rng.randint(1, 6), self.rng.randint(1, 6))
            s.plays = sorted(legal_plays(s.pos, s.roll), key=str)
            if len(s.plays) > 1:
                s.stage = "move"
                s.turn_no += 1
                return
            if s.plays[0].moves:  # only one legal play: make it
                only = s.plays[0]
                s.log.append(f"You rolled {s.roll[0]}-{s.roll[1]}: forced {only}.")
                won = result(only.after)
                if won:
                    self._end_game(s, won)
                    return
                s.pos = only.after
            else:
                s.log.append(f"You rolled {s.roll[0]}-{s.roll[1]}: no legal move.")
            if self._bot_turn(s):
                return

    def _bot_turn(self, s: BGState) -> bool:
        """The bot plays. Returns True if the game ended."""
        theirs = s.pos.flip()
        roll = (self.rng.randint(1, 6), self.rng.randint(1, 6))
        play = self.bot(theirs, roll)
        after = play.after if play else theirs
        text = self._from_hero_side(play) if play else "no legal move"
        s.log.append(f"Bot rolled {roll[0]}-{roll[1]}: {text}.")
        won = result(after)
        if won:
            self._end_game(s, -won)
            return True
        s.pos = after.flip()
        return False

    @staticmethod
    def _from_hero_side(play: Play) -> str:
        """The bot's play in the hero's point numbers (O moves from 1 towards 24)."""
        parts = []
        for m in play.moves:
            a = "bar" if m.src == 25 else str(25 - m.src)
            b = "off" if m.dst == 0 else str(25 - m.dst)
            parts.append(f"{a}/{b}{'*' if m.hit else ''}")
        return " ".join(parts)

    def _end_game(self, s: BGState, points: int) -> None:
        kind = {1: "single game", 2: "gammon", 3: "backgammon"}[abs(points)]
        s.log.append(f"{'You win' if points > 0 else 'The bot wins'} a {kind}: {points:+d}.")
        s.net += points
        s.round_no += 1
        if s.round_no >= s.rounds:
            s.stage = "done"
        else:
            self._new_game(s)

    def lesson(self, s: BGState, q: Question) -> str:
        """Training wheels: the engine's top plays and the shots each one leaves."""
        if q.category != "checker-play":
            return ""
        scores = self._engine_scores(s)
        by_name = {str(p): p for p in s.plays}
        top = sorted(scores, key=lambda k: -scores[k])[:3]
        lines = ["engine's top plays (shots = rolls of 36 that hit one of your blots):"]
        for name in top:
            left = shots.any_shot_rolls(by_name[name].after)
            lines.append(f"  {name}: score {scores[name]:+.2f}, leaves {left} shots")
        return "\n".join(lines)

    def judge(self, s: BGState, q: Question, answer: Any) -> str:
        if q.category != "checker-play" or answer is None:
            return ""
        play = next(p for p in s.plays if str(p) == answer)
        left = shots.any_shot_rolls(play.after)
        return f"{answer}: engine score {bots.evaluate(play.after):+.2f}, leaves {left} shots."

    def _engine_scores(self, s: BGState) -> dict[str, float]:
        return {str(p): bots.evaluate(p.after) for p in s.plays}

    def _exposed_blot(self, pos: Position) -> int | None:
        """The hero's blot with the most shots against it, if any can be hit."""
        best, best_shots = None, 0
        for point in shots.blots(pos):
            n = shots.shots(pos, point)
            if n > best_shots:
                best, best_shots = point, n
        return best

    # --- spots ------------------------------------------------------------------------

    def _new_spot(self, s: BGState) -> Spot:
        kind = ("shots",) if s.mode == "shots" else ("bearoff", "race")
        k = kind[s.round_no % len(kind)]
        if k == "shots":
            return self._shot_spot()
        if k == "bearoff":
            return self._bearoff_spot()
        leader = self.rng.randint(50, 140)
        trailer = round(leader * (1 + self.rng.uniform(0.0, 0.2)))
        return Spot("race", leader=leader, trailer=trailer)

    def _shot_spot(self) -> Spot:
        while True:
            pos = start()
            for _ in range(self.rng.randint(4, 24)):
                roll = (self.rng.randint(1, 6), self.rng.randint(1, 6))
                play = (
                    bots.greedy_bot(pos, roll)
                    if self.rng.random() < 0.7
                    else (bots.random_bot(self.rng)(pos, roll))
                )
                after = play.after if play else pos
                if result(after):
                    break
                pos = after.flip()
            else:
                mine = pos.flip()  # the side that just moved
                candidates = [p for p in shots.blots(mine) if 0 < shots.shots(mine, p) < 36]
                if candidates:
                    return Spot("shots", pos=mine, blot=self.rng.choice(candidates))

    def _bearoff_spot(self) -> Spot:
        def side() -> tuple[int, ...]:
            n = self.rng.randint(2, 6)
            home = [0] * 6
            for _ in range(n):
                home[self.rng.randint(0, 5)] += 1
            return tuple(home)

        return Spot("bearoff", mine=side(), theirs=side())

    # --- the contract -------------------------------------------------------------------

    def legal_actions(self, s: BGState) -> list[str]:
        return [] if self.is_terminal(s) else ["next"]

    def apply(self, s: BGState, action: str) -> BGState:
        if action != "next" or self.is_terminal(s):
            raise ValueError(f"illegal action {action!r}")
        s.asked = 0
        if s.stage == "spot":
            s.round_no += 1
            if s.round_no >= s.rounds:
                s.stage = "done"
            else:
                s.spot = self._new_spot(s)
            return s
        s.log = []
        if s.stage == "move":
            play = next(p for p in s.plays if str(p) == s.pending)
            s.log.append(f"You played {s.roll[0]}-{s.roll[1]}: {play}.")
            won = result(play.after)
            if won:
                self._end_game(s, won)
                return s
            s.pos = play.after
            if self._exposed_blot(s.pos) is not None:
                s.stage = "shot"
                return s
        if self._bot_turn(s):
            return s
        self._hero_roll(s)
        return s

    def is_terminal(self, s: BGState) -> bool:
        return s.stage == "done"

    def result(self, s: BGState) -> float:
        return float(s.net) if s.mode == "play" else float(s.right)

    def questions(self, s: BGState) -> list[Question]:
        if s.stage == "move":
            qs = []
            if s.turn_no % 4 == 1:
                qs.append(self._pip_question(s, "yours", s.pos.pips()))
            listing = "\n".join(f"  {i + 1:>2}. {p}" for i, p in enumerate(s.plays))
            qs.append(
                Question(
                    id=f"g{s.round_no}-t{s.turn_no}",
                    kind=Kind.DECISION,
                    prompt=f"You rolled {s.roll[0]}-{s.roll[1]}. Your play (number or moves)?\n"
                    + listing,
                    category="checker-play",
                    choices=tuple(str(p) for p in s.plays),
                    tolerance=TIE,
                    tip="Make points, avoid leaving blots within 6 pips of enemy checkers, "
                    "and hit when it costs little.",
                )
            )
            return qs
        if s.stage == "shot":
            point = self._exposed_blot(s.pos)
            return [self._shot_question(s, s.pos, point, "after your play")]
        sp = s.spot
        n = s.round_no
        if sp.kind == "shots":
            return [
                self._pip_question(s, "yours", sp.pos.pips()),
                self._pip_question(s, "theirs", sp.pos.opp_pips()),
                self._shot_question(s, sp.pos, sp.blot, "the bot is about to roll"),
            ]
        if sp.kind == "bearoff":
            return [
                Question(
                    id=f"c{n}-pips",
                    kind=Kind.POINT,
                    prompt="Your pip count?",
                    category="pip-count",
                    tip="Multiply the checkers on each point by the point number and add.",
                ),
                Question(
                    id=f"c{n}-win",
                    kind=Kind.POINT,
                    prompt="You are on roll. Your chance of winning (0-1)?",
                    category="bearoff-win",
                    tolerance=0.04,
                    tip="Count rolls, not pips: how many turns does each side need?",
                ),
                Question(
                    id=f"c{n}-double",
                    kind=Kind.DECISION,
                    prompt="Dead cube, money play: double?",
                    category="cube-double",
                    choices=("double", "no double"),
                    params={"keys": {"d": "double", "n": "no double"}},
                    tolerance=0.005,
                    tip="With a dead cube, double whenever you are a favourite (p > 50%); "
                    "the opponent takes if your chance is 75% or less.",
                ),
                Question(
                    id=f"c{n}-take",
                    kind=Kind.DECISION,
                    prompt="Now swap: the bot is on roll in this position and doubles you. "
                    "Take or drop?",
                    category="cube-take",
                    choices=("take", "drop"),
                    params={"keys": {"t": "take", "d": "drop"}},
                    tolerance=0.005,
                    tip="Take with at least 25% to win: −1 for dropping against 4p − 2 for taking.",
                ),
            ]
        return [
            Question(
                id=f"c{n}-lead",
                kind=Kind.POINT,
                prompt="Your race lead as a percentage of your pip count?",
                category="race-lead",
                tolerance=1.0,
                params={"unit": "percent"},
                tip="(their pips − your pips) / your pips.",
            ),
            Question(
                id=f"c{n}-rule-double",
                kind=Kind.DECISION,
                prompt="By the 8-9-12 rule (initial double), double?",
                category="race-double",
                choices=("double", "no double"),
                params={"keys": {"d": "double", "n": "no double"}},
                tip="Leader: double at 8% or more, redouble at 9%; trailer takes up to 12%.",
            ),
            Question(
                id=f"c{n}-rule-take",
                kind=Kind.DECISION,
                prompt="If you doubled, should the bot take?",
                category="race-take",
                choices=("take", "drop"),
                params={"keys": {"t": "take", "d": "drop"}},
                tip="The trailer takes when behind by 12% or less.",
            ),
        ]

    def _pip_question(self, s: BGState, whose: str, value: int) -> Question:
        return Question(
            id=f"r{s.round_no}-t{s.turn_no}-pips-{whose}",
            kind=Kind.POINT,
            prompt=f"Pip count ({whose})?",
            category="pip-count",
            params={"value": value},
            tip="Count by points: checkers × point number; the start is 167.",
        )

    def _shot_question(self, s: BGState, pos: Position, point: int, when: str) -> Question:
        return Question(
            id=f"r{s.round_no}-t{s.turn_no}-shot{point}",
            kind=Kind.POINT,
            prompt=f"Your blot on point {point} ({when}): how many of the 36 rolls hit it?",
            category="shots",
            params={"point": point},
            tip="Direct shots (1-6 away): 11 + one for each smaller combination; beyond 6, "
            "only combinations, and blocked points cut them.",
        )

    def truth(self, s: BGState, q: Question) -> Any:
        c = q.category
        if c == "checker-play":
            return self._engine_scores(s)
        if c == "pip-count":
            if "value" in q.params:
                return float(q.params["value"])
            return float(bearoff.pips(s.spot.mine))
        if c == "shots":
            pos = s.pos if s.stage == "shot" else s.spot.pos
            return float(shots.shots(pos, q.params["point"]))
        sp = s.spot
        if c == "bearoff-win":
            return bearoff.win_chance(sp.mine, sp.theirs)
        if c == "cube-double":
            v = bearoff.cube_values(bearoff.win_chance(sp.mine, sp.theirs))
            return {"double": v["double"], "no double": v["no double"]}
        if c == "cube-take":
            return bearoff.take_values(bearoff.win_chance(sp.theirs, sp.mine))
        rule = bearoff.race_rule(sp.leader, sp.trailer)
        if c == "race-lead":
            return 100 * rule["lead"]
        if c == "race-double":
            return {"double": float(rule["double"]), "no double": float(not rule["double"])}
        if c == "race-take":
            return {"take": float(rule["take"]), "drop": float(not rule["take"])}
        raise ValueError(f"unknown question {q.id}")

    def explain(self, s: BGState, q: Question) -> str:
        c = q.category
        if c == "checker-play":
            scores = self._engine_scores(s)
            ranked = sorted(scores, key=lambda k: -scores[k])[:3]
            top = "; ".join(f"{k} ({scores[k]:+.2f})" for k in ranked)
            return f"Engine scores (a heuristic, not exact equity) — best: {top}."
        if c == "pip-count":
            return f"Pip count {q.params.get('value', bearoff.pips(s.spot.mine) if s.spot else 0)}."
        if c == "shots":
            pos = s.pos if s.stage == "shot" else s.spot.pos
            rolls = shots.hitting_rolls(pos, q.params["point"])
            listed = " ".join(f"{a}-{b}" for a, b in rolls)
            return f"Hitting rolls: {listed} = {shots.shots(pos, q.params['point'])} of 36."
        sp = s.spot
        if c == "bearoff-win":
            p = bearoff.win_chance(sp.mine, sp.theirs)
            return (
                f"Your expected rolls to finish {bearoff.expected_rolls(sp.mine):.2f}, theirs "
                f"{bearoff.expected_rolls(sp.theirs):.2f}; you roll first. Exact: {p:.3f}."
            )
        if c == "cube-double":
            p = bearoff.win_chance(sp.mine, sp.theirs)
            v = bearoff.cube_values(p)
            return (
                f"p = {p:.3f}. No double: 2p − 1 = {v['no double']:+.3f}. Double: they take "
                f"({v['if taken']:+.3f}) or drop (+1); they choose the smaller, "
                f"{v['double']:+.3f}. "
                "With a live cube you would wait for a stronger position (the doubling "
                "window is about 70-78%), because owning the cube has value."
            )
        if c == "cube-take":
            p = bearoff.win_chance(sp.theirs, sp.mine)
            return (
                f"The bot's chance on roll is {p:.3f}, so yours is {1 - p:.3f}. Take: "
                f"2 × (1 − 2p) = {2 * (1 - 2 * p):+.3f}; drop: −1. Take with at least 25%."
            )
        rule = bearoff.race_rule(sp.leader, sp.trailer)
        if c == "race-lead":
            return f"({sp.trailer} − {sp.leader}) / {sp.leader} = {100 * rule['lead']:.1f}%."
        return (
            f"Lead {100 * rule['lead']:.1f}%: double {'yes' if rule['double'] else 'no'} "
            f"(≥ 8%), take {'yes' if rule['take'] else 'no'} (≤ 12%). A rule of thumb for long "
            "races, not an exact answer."
        )

    def observe(
        self, s: BGState, q: Question, answer: Any, score: Score, seconds: float
    ) -> BGState:
        s.asked += 1
        s.right += bool(score.correct)
        if q.category == "checker-play":
            s.pending = answer
            s.decisions += 1
            s.best += bool(score.correct)
            s.lost += score.error
            if score.error > TIE:
                s.mistakes.append(
                    (score.error, f"{s.roll[0]}-{s.roll[1]}: {answer} (−{score.error:.2f})")
                )
        return s

    def describe(self, s: BGState) -> str:
        if s.stage == "spot":
            sp = s.spot
            head = f"Spot {s.round_no + 1} of {s.rounds}."
            if sp.kind == "shots":
                return (
                    f"{head} You (X) have just moved; the bot (O) moves from 1 towards 24.\n"
                    + render(sp.pos)
                )
            if sp.kind == "bearoff":
                rows = [
                    f"  point {p}:  you {sp.mine[p - 1]}   bot {sp.theirs[p - 1]}"
                    for p in range(6, 0, -1)
                ]
                return (
                    f"{head} Bear-off, no contact. Checkers on each home point "
                    "(both of you have borne some off already, so no gammons):\n" + "\n".join(rows)
                )
            return (
                f"{head} A long race, no contact. You are on roll with {sp.leader} pips; "
                f"the bot has {sp.trailer}."
            )
        lines = list(s.log) if s.asked == 0 else []
        if s.stage in ("move", "shot"):
            lines.append(f"Game {s.round_no + 1} of {s.rounds}, turn {s.turn_no} | net {s.net:+d}")
            lines.append(render(s.pos))
        return "\n".join(lines)

    def summary(self, s: BGState) -> str:
        if s.mode != "play":
            return f"{s.right} answers right."
        lines = list(s.log) + [""]
        lines.append(f"Games: {s.round_no}, net points {s.net:+d} against the {s.bot} bot.")
        if s.decisions:
            lines.append(
                f"Plays: {s.best} of {s.decisions} matched the engine's choice; engine points "
                f"given up {s.lost:.2f} (engine's opinion, not exact equity)."
            )
        worst = sorted(s.mistakes, key=lambda m: -m[0])[:3]
        if worst:
            lines.append("Plays the engine liked least:")
            lines += [f"  {text}" for _, text in worst]
        return "\n".join(lines)
