"""Poker: Kuhn and Leduc against solved or exploitable bots, and Hold'em spots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from . import equity as eq
from .cfr import CFRPlus, Tree
from .evaluator import describe, evaluate, names
from .games import RANK_NAMES, Kuhn, Leduc

MODES = ("kuhn", "leduc", "spots")
BOTS = ("cfr", "station", "maniac")
SOLVE_ITERATIONS = {"kuhn": 2000, "leduc": 1500}
TIE = 0.005  # chips: actions this close in EV count as equally good
NAME_KEYS = {"check": "k", "bet": "b", "call": "c", "fold": "f", "raise": "r"}


@lru_cache(maxsize=4)
def solved(game: str) -> tuple[Tree, np.ndarray]:
    tree = Tree(Kuhn() if game == "kuhn" else Leduc())
    return tree, CFRPlus(tree).solve(SOLVE_ITERATIONS[game])


def style_strategy(tree: Tree, style: str) -> np.ndarray:
    """A pure exploitable strategy: 'station' calls but never bets, 'maniac' always bets."""
    s = np.zeros((len(tree.infosets), tree.max_actions))
    for i, acts in enumerate(tree.infoset_actions):
        key = tree.infosets[i]
        history = key.split(":", 1)[1]
        facing = history.split("/")[-1].endswith(("b", "r"))
        if tree.rules.name == "kuhn":
            pick = ("b" if facing else "p") if style == "station" else "b"
        elif style == "station":
            pick = "c"
        else:
            pick = "r" if "r" in acts else "c"
        s[i, acts.index(pick)] = 1.0
    return s


@lru_cache(maxsize=16)
def bot_and_best_response(game: str, bot: str, hero: int) -> tuple[np.ndarray, np.ndarray, float]:
    """The bot's strategy, the hero's best-response action values, and the BR value."""
    tree, eq_strategy = solved(game)
    strategy = eq_strategy if bot == "cfr" else style_strategy(tree, bot)
    value, q = tree.best_response(strategy, hero)
    return strategy, q, value


def action_name(game: str, history: str, a: str) -> str:
    seq = history.split("/")[-1]
    facing = seq.endswith("b" if game == "kuhn" else "r")
    if game == "kuhn":
        return ("fold" if facing else "check") if a == "p" else ("call" if facing else "bet")
    return {"c": "call" if facing else "check", "r": "raise" if facing else "bet", "f": "fold"}[a]


@dataclass
class Spot:
    hero: list[int]
    villain: list[int]
    board: list[int]
    pot: int  # before the villain's all-in bet
    bet: int
    ask_mdf: bool


@dataclass
class PokerState:
    mode: str
    hands: int
    bot: str = "cfr"
    hand_no: int = 0
    hero: int = 0  # seat this hand: 0 acts first
    deal: tuple[int, ...] = ()
    history: str = ""
    net: float = 0.0
    log: list[str] = field(default_factory=list)
    prev_log: list[str] = field(default_factory=list)
    pending: str | None = None
    asked: int = 0
    decisions: int = 0
    right: int = 0
    ev_lost: float = 0.0
    spot: Spot | None = None
    done: bool = False


class Poker(GameModule):
    name = "poker"
    title = "Poker"

    # --- setup -------------------------------------------------------------------

    def init(self, rng: Rng, config: Mapping[str, Any]) -> PokerState:
        mode = str(config.get("mode", "kuhn"))
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
        bot = str(config.get("bot", "cfr"))
        if bot not in BOTS:
            raise ValueError(f"unknown bot {bot!r}; choose from {', '.join(BOTS)}")
        hands = int(config.get("hands", 10 if mode == "spots" else 20))
        if hands < 1:
            raise ValueError("hands must be at least 1")
        self.rng = rng
        s = PokerState(mode=mode, hands=hands, bot=bot)
        if mode == "spots":
            s.spot = self._new_spot()
        else:
            self._new_hand(s)
        return s

    @property
    def rules(self):
        return self._tree.rules

    # --- Kuhn and Leduc --------------------------------------------------------------

    def _new_hand(self, s: PokerState) -> None:
        self._tree, _ = solved(s.mode)
        s.hero = s.hand_no % 2
        weights = list(self._tree.weights)
        s.deal = self._tree.deals[self.rng.weighted_index(weights)]
        s.history = ""
        s.log = []
        s.asked = 0
        self._bot_moves(s)

    def _strategy(self, s: PokerState) -> np.ndarray:
        return bot_and_best_response(s.mode, s.bot, s.hero)[0]

    def _infoset(self, s: PokerState, player: int) -> int:
        key = self.rules.infoset(player, s.history, s.deal)
        return self._tree.infoset_index[key]

    def _actions(self, s: PokerState) -> list[str]:
        return self.rules.actions(s.history)

    def _bot_moves(self, s: PokerState) -> None:
        """Let the bot act until it is the hero's turn or the hand is over."""
        while self._actions(s) and self.rules.player(s.history) != s.hero:
            acts = self._actions(s)
            probs = self._strategy(s)[self._infoset(s, 1 - s.hero), : len(acts)]
            a = acts[self.rng.weighted_index(list(probs))]
            s.log.append(f"Bot: {action_name(s.mode, s.history, a)}.")
            s.history = (
                self.rules.child(s.history, a) if hasattr(self.rules, "child") else s.history + a
            )
        if not self._actions(s):
            self._settle(s)

    def _settle(self, s: PokerState) -> None:
        p0 = self.rules.payoff(s.history, s.deal)
        mine = p0 if s.hero == 0 else -p0
        s.net += mine
        cards = self._show_cards(s, reveal=True)
        s.prev_log = [f"Hand {s.hand_no + 1}: {cards}"] + [f"  {line}" for line in s.log]
        s.prev_log.append(
            f"  You {'win' if mine > 0 else 'lose' if mine < 0 else 'split'} {abs(mine):g}."
        )
        s.hand_no += 1
        if s.hand_no >= s.hands:
            s.done = True
        else:
            self._new_hand(s)

    def _show_cards(self, s: PokerState, reveal: bool = False) -> str:
        mine = RANK_NAMES[s.deal[s.hero]]
        text = f"you {mine}"
        if reveal:
            text += f", bot {RANK_NAMES[s.deal[1 - s.hero]]}"
        if s.mode == "leduc" and ("/" in self.rules._norm(s.history) or reveal):
            if "/" in self.rules._norm(s.history):
                text += f", public {RANK_NAMES[s.deal[2]]}"
        return text

    def _decision_question(self, s: PokerState) -> Question:
        acts = self._actions(s)
        choices = tuple(action_name(s.mode, s.history, a) for a in acts)
        seat = "first" if s.hero == 0 else "second"
        pot = ""
        if s.mode == "leduc":
            paid = self.rules.contributions(self.rules._norm(s.history))
            pot = f" Pot {sum(paid)} (you put in {paid[s.hero]})."
        return Question(
            id=f"h{s.hand_no}-{s.history}",
            kind=Kind.DECISION,
            prompt=f"You act {seat}; {self._show_cards(s)}.{pot} Your move?",
            category=f"{s.mode}-decision",
            choices=choices,
            tolerance=TIE,
            params={
                "keys": {NAME_KEYS[c]: c for c in choices},
                "codes": dict(zip(choices, acts, strict=True)),
            },
            tip="Against a balanced opponent, mix bluffs with value bets; against a "
            "calling station, stop bluffing and bet your good hands; against a maniac, "
            "call down lighter.",
        )

    def _q_values(self, s: PokerState) -> dict[str, float]:
        _, q, _ = bot_and_best_response(s.mode, s.bot, s.hero)
        i = self._infoset(s, s.hero)
        acts = self._actions(s)
        return {action_name(s.mode, s.history, a): float(q[i, k]) for k, a in enumerate(acts)}

    # --- Hold'em spots --------------------------------------------------------------

    def _new_spot(self) -> Spot:
        while True:
            board_len = self.rng.choice((3, 4))
            drawn = self.rng.sample(range(52), 4 + board_len)
            hero, villain, board = drawn[:2], drawn[2:4], drawn[4:]
            if evaluate(hero + board) >= evaluate(villain + board):
                continue  # spots where you are behind and drawing
            if not eq.outs(hero, villain, board):
                continue
            pot = 10 * self.rng.randint(2, 20)
            bet = round(pot * self.rng.choice((1 / 3, 1 / 2, 2 / 3, 3 / 4, 1, 3 / 2)))
            return Spot(hero, villain, board, pot, bet, self.rng.random() < 0.5)

    def _spot_equity(self, s: PokerState) -> float:
        sp = s.spot
        return float(eq.exact(sp.hero, sp.villain, sp.board).equity)

    def _spot_questions(self, s: PokerState) -> list[Question]:
        sp = s.spot
        street = "flop" if len(sp.board) == 3 else "turn"
        unseen = 52 - 4 - len(sp.board)
        n = s.hand_no
        qs = [
            Question(
                id=f"s{n}-outs",
                kind=Kind.POINT,
                prompt=f"How many outs do you have for the next card ({unseen} unseen)?",
                category="outs",
                tip="Count the cards that put you ahead; watch for outs that also help him.",
            ),
            Question(
                id=f"s{n}-equity",
                kind=Kind.POINT,
                prompt=f"Your equity to the river from the {street} (0-1)?",
                category="equity",
                tolerance=0.03,
                tip="Rule of 2 and 4: outs × 2% per card to come (× 4% on the flop).",
            ),
            Question(
                id=f"s{n}-odds",
                kind=Kind.POINT,
                prompt=f"Pot odds: the equity you need to call {sp.bet} (0-1)?",
                category="pot-odds",
                tolerance=0.01,
                tip="Call ÷ (final pot) = bet ÷ (pot + 2 × bet).",
            ),
            Question(
                id=f"s{n}-call",
                kind=Kind.DECISION,
                prompt="Call or fold?",
                category="call-fold",
                choices=("call", "fold"),
                params={"keys": {"c": "call", "f": "fold"}},
                tip="Call when equity × final pot is more than the call.",
            ),
        ]
        if sp.ask_mdf:
            qs.append(
                Question(
                    id=f"s{n}-mdf",
                    kind=Kind.POINT,
                    prompt=f"If he bets {sp.bet} into {sp.pot} with any two cards, what share "
                    "of your hands must you defend so his bluffs don't profit (MDF)?",
                    category="mdf",
                    tolerance=0.02,
                    tip="MDF = pot ÷ (pot + bet).",
                )
            )
        else:
            qs.append(
                Question(
                    id=f"s{n}-bluff",
                    kind=Kind.POINT,
                    prompt=f"Turn it round: if you bluff {sp.bet} into {sp.pot}, how often must "
                    "he fold for it to break even?",
                    category="bluff-breakeven",
                    tolerance=0.02,
                    tip="Bet ÷ (pot + bet): risk over risk plus reward.",
                )
            )
        return qs

    # --- the contract ------------------------------------------------------------------

    def legal_actions(self, s: PokerState) -> list[str]:
        return [] if self.is_terminal(s) else ["next"]

    def apply(self, s: PokerState, action: str) -> PokerState:
        if action != "next" or self.is_terminal(s):
            raise ValueError(f"illegal action {action!r}")
        if s.mode == "spots":
            s.hand_no += 1
            if s.hand_no >= s.hands:
                s.done = True
            else:
                s.spot = self._new_spot()
            return s
        a = s.pending
        s.log.append(f"You: {action_name(s.mode, s.history, a)}.")
        s.history = (
            self.rules.child(s.history, a) if hasattr(self.rules, "child") else s.history + a
        )
        s.pending = None
        s.asked = 0
        self._bot_moves(s)
        return s

    def is_terminal(self, s: PokerState) -> bool:
        return s.done

    def result(self, s: PokerState) -> float:
        """Chips won (spots: right answers)."""
        return float(s.right) if s.mode == "spots" else s.net

    def questions(self, s: PokerState) -> list[Question]:
        if s.mode == "spots":
            return self._spot_questions(s)
        return [self._decision_question(s)]

    def truth(self, s: PokerState, q: Question) -> Any:
        c = q.category
        if c.endswith("-decision"):
            return self._q_values(s)
        sp = s.spot
        if c == "outs":
            return float(len(eq.outs(sp.hero, sp.villain, sp.board)))
        if c == "equity":
            return self._spot_equity(s)
        if c == "pot-odds":
            return sp.bet / (sp.pot + 2 * sp.bet)
        if c == "call-fold":
            e = self._spot_equity(s)
            return {"call": e * (sp.pot + 2 * sp.bet) - sp.bet, "fold": 0.0}
        if c == "mdf":
            return sp.pot / (sp.pot + sp.bet)
        if c == "bluff-breakeven":
            return sp.bet / (sp.pot + sp.bet)
        raise ValueError(f"unknown question {q.id}")

    def explain(self, s: PokerState, q: Question) -> str:
        c = q.category
        if c.endswith("-decision"):
            q_values = self._q_values(s)
            best = max(q_values, key=q_values.get)
            text = "EV against this bot: " + ", ".join(f"{a} {v:+.3f}" for a, v in q_values.items())
            tied = [a for a, v in q_values.items() if q_values[best] - v <= TIE]
            if len(tied) > 1:
                text += (
                    f". {' and '.join(tied)} are equally good here: an equilibrium opponent "
                    "makes you indifferent, which is why mixing them is right."
                )
            else:
                text += f". Best: {best}."
            tree, eq_strategy = solved(s.mode)
            i = self._infoset(s, s.hero)
            acts = self._actions(s)
            mix = ", ".join(
                f"{action_name(s.mode, s.history, a)} {eq_strategy[i, k]:.0%}"
                for k, a in enumerate(acts)
            )
            return text + f" Equilibrium mix here: {mix}."
        sp = s.spot
        if c == "outs":
            o = eq.outs(sp.hero, sp.villain, sp.board)
            unseen = 52 - 4 - len(sp.board)
            share = len(o) / unseen
            return f"{len(o)} outs: {names(sorted(o))}. Next card: {len(o)}/{unseen} = {share:.1%}."
        if c == "equity":
            e = eq.exact(sp.hero, sp.villain, sp.board)
            n_outs = len(eq.outs(sp.hero, sp.villain, sp.board))
            unseen = 52 - 4 - len(sp.board)
            if len(sp.board) == 3:
                rule = (
                    f"rule of 4: {n_outs} × 4% = {4 * n_outs}%; "
                    f"{n_outs} outs twice: {eq.two_card_chance(n_outs, unseen):.1%}"
                )
            else:
                rule = f"rule of 2: {n_outs} × 2% = {2 * n_outs}%"
            return (
                f"Exact over all {e.boards} boards: win {float(e.win):.1%}, tie "
                f"{float(e.tie):.1%} → equity {float(e.equity):.1%} ({rule}). Outs can also "
                "lose to a better hand, and runner-runner hands add equity."
            )
        if c == "pot-odds":
            return (
                f"You call {sp.bet} to win a final pot of {sp.pot} + {sp.bet} + {sp.bet} = "
                f"{sp.pot + 2 * sp.bet}: {sp.bet}/{sp.pot + 2 * sp.bet} = "
                f"{sp.bet / (sp.pot + 2 * sp.bet):.1%}."
            )
        if c == "call-fold":
            e = self._spot_equity(s)
            final = sp.pot + 2 * sp.bet
            return (
                f"EV(call) = {e:.3f} × {final} − {sp.bet} = {e * final - sp.bet:+.1f}; "
                f"EV(fold) = 0. Villain had {names(sp.villain)} "
                f"({describe(evaluate(sp.villain + sp.board))})."
            )
        if c == "mdf":
            return f"{sp.pot} / ({sp.pot} + {sp.bet}) = {sp.pot / (sp.pot + sp.bet):.1%}."
        if c == "bluff-breakeven":
            return f"{sp.bet} / ({sp.pot} + {sp.bet}) = {sp.bet / (sp.pot + sp.bet):.1%}."
        raise ValueError(f"unknown question {q.id}")

    def observe(
        self, s: PokerState, q: Question, answer: Any, score: Score, seconds: float
    ) -> PokerState:
        s.asked += 1
        if q.kind is Kind.DECISION:
            s.decisions += 1
            s.ev_lost += score.error
            s.right += bool(score.correct)
            if q.category.endswith("-decision"):
                s.pending = q.params["codes"][answer]
        elif score.correct:
            s.right += 1
        return s

    # --- text ----------------------------------------------------------------------

    def describe(self, s: PokerState) -> str:
        if s.mode == "spots":
            sp = s.spot
            return (
                f"Spot {s.hand_no + 1} of {s.hands}. You: {names(sp.hero)}. "
                f"Villain (shown): {names(sp.villain)}. Board: {names(sp.board)}.\n"
                f"Pot {sp.pot}; villain goes all in for {sp.bet}."
            )
        lines = []
        if s.asked == 0 and s.prev_log:
            lines += s.prev_log + [""]
        bot = {"cfr": "equilibrium (CFR)", "station": "calling station", "maniac": "maniac"}[s.bot]
        lines.append(
            f"{s.mode.capitalize()} hand {s.hand_no + 1} of {s.hands} | bot: {bot} | net {s.net:+g}"
        )
        lines += [f"  {line}" for line in s.log]
        return "\n".join(lines)

    def summary(self, s: PokerState) -> str:
        if s.mode == "spots":
            return f"Spots: {s.right} answers right; EV lost on calls {s.ev_lost:.1f} chips."
        lines = list(s.prev_log) + [""]
        per = s.net / max(s.hand_no, 1)
        lines.append(f"{s.hand_no} hands, net {s.net:+g} chips ({per:+.3f} per hand).")
        tree, eq_strategy = solved(s.mode)
        v0 = tree.value(eq_strategy)
        lines.append(
            f"Equilibrium value: {v0:+.4f} per hand acting first, {-v0:+.4f} acting second "
            f"(average 0 over both seats)."
        )
        best = [bot_and_best_response(s.mode, s.bot, h)[2] for h in (0, 1)]
        lines.append(
            f"Best possible against this bot: {best[0]:+.3f} first, {best[1]:+.3f} second "
            f"(average {sum(best) / 2:+.3f} per hand)."
        )
        if s.decisions:
            lines.append(
                f"Decisions: {s.right} of {s.decisions} best; EV lost {s.ev_lost:.3f} chips."
            )
        return "\n".join(lines)
