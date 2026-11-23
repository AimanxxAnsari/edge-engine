"""Blackjack: basic strategy, Hi-Lo counting and deviations, with EV-lost review."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from . import count as hilo
from .cards import HILO, VALUE, Rules, Shoe, is_blackjack, label, show, total
from .ev import ACTIONS, Situation, Solver, comp_from_counts, comp_without
from .strategy import table

MODES = ("strategy", "count", "drill")
KEYS = {"h": "hit", "s": "stand", "d": "double", "p": "split", "r": "surrender"}
MAX_HANDS = 4


@lru_cache(maxsize=8)
def chart(rules: Rules) -> dict[str, dict[int, str]]:
    return table(rules, decks=rules.decks)


@dataclass
class Hand:
    cards: list[str]
    bet: float
    done: bool = False
    split: bool = False
    split_aces: bool = False
    doubled: bool = False
    surrendered: bool = False


@dataclass
class BJState:
    mode: str
    rules: Rules
    rounds: int
    shoe: Shoe
    bust_questions: bool
    stage: str = "bet"  # bet | insurance | decide | drill | done
    round_no: int = 0  # rounds finished
    dealer: list[str] = field(default_factory=list)
    hole_seen: bool = False
    hands: list[Hand] = field(default_factory=list)
    active: int = 0
    seen: list[str] = field(default_factory=list)  # cards seen since the shuffle
    last_round: list[str] = field(default_factory=list)  # cards seen in the last round
    base_bet: float = 1.0
    insured: bool = False
    pending: Any = None  # the answer to the current decision
    asked_this_round: int = 0
    net: float = 0.0
    log: list[str] = field(default_factory=list)  # how the current round is going
    prev_log: list[str] = field(default_factory=list)  # how the last round went
    # review
    decisions: int = 0
    right: int = 0
    ev_lost: float = 0.0
    mistakes: list[tuple[float, str]] = field(default_factory=list)
    count_asked: int = 0
    count_right: int = 0
    shuffled: bool = False
    # drill
    batch: int = 4
    drill_cards: list[str] = field(default_factory=list)
    drill_pos: int = 0
    drill_tc: tuple[int, float] = (0, 1.0)


def _flag(config: Mapping[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def parse_rules(config: Mapping[str, Any]) -> Rules:
    payout = config.get("payout", "3:2")
    if isinstance(payout, str) and ":" in payout:
        a, b = payout.split(":")
        payout = int(a) / int(b)
    rules = Rules(
        decks=int(config.get("decks", 6)),
        h17=_flag(config, "h17", False),
        payout=float(payout),
        das=_flag(config, "das", True),
        surrender=_flag(config, "surrender", True),
        resplit=_flag(config, "resplit", True),
        penetration=float(config.get("penetration", 0.75)),
    )
    if rules.decks < 1 or not 0.2 <= rules.penetration <= 0.9 or rules.payout <= 0:
        raise ValueError("need decks >= 1, 0.2 <= penetration <= 0.9 and a positive payout")
    return rules


class Blackjack(GameModule):
    name = "blackjack"
    title = "Blackjack"

    # --- setup -------------------------------------------------------------

    def init(self, rng: Rng, config: Mapping[str, Any]) -> BJState:
        mode = str(config.get("mode", "strategy"))
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
        rules = parse_rules(config)
        rounds = int(config.get("hands", 20))
        if rounds < 1:
            raise ValueError("hands must be at least 1")
        self.rng = rng
        shoe = Shoe(1 if mode == "drill" else rules.decks, rng, rules.penetration)
        state = BJState(
            mode=mode,
            rules=rules,
            rounds=rounds,
            shoe=shoe,
            bust_questions=_flag(config, "bust", mode == "strategy"),
            batch=int(config.get("batch", 4)),
        )
        if mode == "drill":
            if not 1 <= state.batch <= 13:
                raise ValueError("batch must be between 1 and 13")
            state.stage = "drill"
            state.drill_cards = list(shoe.cards)
            state.drill_tc = self._random_tc()
            return state
        chart(rules)  # build once up front
        self._start_round(state)
        return state

    def _random_tc(self) -> tuple[int, float]:
        return self.rng.randint(-12, 12), self.rng.randint(1, 11) / 2

    # --- composition and the truth -------------------------------------------

    def unseen_counts(self, s: BJState) -> list[int]:
        counts = list(s.shoe.counts())
        if s.dealer and not s.hole_seen:
            counts[VALUE[s.dealer[1]] - 1] += 1
        return counts

    def comp(self, s: BJState, hand: Hand) -> tuple[float, ...]:
        if s.mode == "count":
            return comp_from_counts(self.unseen_counts(s))
        known = [VALUE[c] for c in hand.cards] + [VALUE[s.dealer[0]]]
        return comp_without(s.rules.decks, known)

    def situation(self, s: BJState, hand: Hand) -> Situation:
        values = [VALUE[c] for c in hand.cards]
        pair = None
        if len(values) == 2 and values[0] == values[1] and len(s.hands) < MAX_HANDS:
            if not hand.split_aces and (values[0] != 1 or not hand.split):
                pair = values[0]
        return Situation(
            hard=sum(values),
            ace=1 in values,
            up=VALUE[s.dealer[0]],
            pair=pair,
            first=len(values) == 2 and not hand.doubled,
            split_hand=hand.split,
        )

    def evs(self, s: BJState, hand: Hand) -> dict[str, float]:
        return Solver(self.comp(s, hand), s.rules).evs(self.situation(s, hand))

    def running_count(self, s: BJState) -> int:
        return hilo.running_count(s.seen)

    def true_count(self, s: BJState) -> float:
        return hilo.true_count(self.running_count(s), sum(self.unseen_counts(s)))

    def p_ten(self, s: BJState) -> float:
        if s.mode == "count":
            counts = self.unseen_counts(s)
            return counts[9] / sum(counts)
        known = [VALUE[c] for c in s.hands[0].cards] + [VALUE[s.dealer[0]]]
        return comp_without(s.rules.decks, known)[9]

    # --- rounds --------------------------------------------------------------

    def _start_round(self, s: BJState) -> None:
        s.shuffled = False
        if s.shoe.needs_shuffle():
            s.shoe.shuffle()
            s.seen = []
            s.shuffled = True
        s.dealer, s.hands, s.active = [], [], 0
        s.hole_seen, s.insured, s.pending = False, False, None
        s.asked_this_round = 0
        s.base_bet = 1.0
        if s.mode == "count":
            s.stage = "bet"
        else:
            self._deal(s)

    def _draw(self, s: BJState, seen: bool = True) -> str:
        card = s.shoe.draw()
        if seen:
            s.seen.append(card)
            s.last_round.append(card)
        return card

    def _deal(self, s: BJState) -> None:
        s.last_round = []
        p1, up = self._draw(s), self._draw(s)
        p2, hole = self._draw(s), self._draw(s, seen=False)
        s.hands = [Hand([p1, p2], s.base_bet)]
        s.dealer = [up, hole]
        s.log = []
        if up == "A":
            s.stage = "insurance"
        else:
            self._peek(s)

    def _reveal_hole(self, s: BJState) -> None:
        if not s.hole_seen:
            s.hole_seen = True
            s.seen.append(s.dealer[1])
            s.last_round.append(s.dealer[1])

    def _peek(self, s: BJState) -> None:
        """After insurance: dealer and player blackjacks end the round at once."""
        hand = s.hands[0]
        bet = hand.bet
        if s.insured:
            if is_blackjack(s.dealer):
                s.net += bet
                s.log.append(f"Insurance wins: +{bet:g}")
            else:
                s.net -= bet / 2
                s.log.append(f"Insurance loses: −{bet / 2:g}")
        if VALUE[s.dealer[0]] in (1, 10) and is_blackjack(s.dealer):
            self._reveal_hole(s)
            if is_blackjack(hand.cards):
                s.log.append("Both have blackjack: push.")
            else:
                s.net -= bet
                s.log.append(f"Dealer has blackjack: −{bet:g}")
            self._end_round(s)
        elif is_blackjack(hand.cards):
            self._reveal_hole(s)
            win = bet * s.rules.payout
            s.net += win
            s.log.append(f"Blackjack! +{win:g}")
            self._end_round(s)
        else:
            s.stage = "decide"

    def _apply_decision(self, s: BJState, action: str) -> None:
        hand = s.hands[s.active]
        if action == "hit":
            hand.cards.append(self._draw(s))
            if total(hand.cards)[0] >= 21:
                hand.done = True
        elif action == "stand":
            hand.done = True
        elif action == "double":
            hand.bet *= 2
            hand.doubled = True
            hand.cards.append(self._draw(s))
            hand.done = True
        elif action == "surrender":
            hand.surrendered = True
            hand.done = True
        elif action == "split":
            aces = hand.cards[0] == "A"
            new = Hand([hand.cards.pop()], hand.bet, split=True, split_aces=aces)
            hand.split, hand.split_aces = True, aces
            hand.cards.append(self._draw(s))
            new.cards.append(self._draw(s))
            s.hands.insert(s.active + 1, new)
            for h in (hand, new):
                if aces or total(h.cards)[0] == 21:
                    h.done = True
        else:
            raise ValueError(f"unknown action {action!r}")
        for i, h in enumerate(s.hands):
            if not h.done:
                s.active = i
                s.stage = "decide"
                return
        self._dealer_plays(s)

    def _dealer_plays(self, s: BJState) -> None:
        self._reveal_hole(s)
        live = [h for h in s.hands if not h.surrendered and total(h.cards)[0] <= 21]
        if live:
            while True:
                t, soft = total(s.dealer)
                if t > 17 or (t == 17 and not (soft and s.rules.h17)):
                    break
                s.dealer.append(self._draw(s))
        d, _ = total(s.dealer)
        s.log.append(f"Dealer: {show(s.dealer)}")
        for h in s.hands:
            t, _ = total(h.cards)
            if h.surrendered:
                result, note = -h.bet / 2, "surrendered"
            elif t > 21:
                result, note = -h.bet, "bust"
            elif d > 21 or t > d:
                result, note = h.bet, "win"
            elif t < d:
                result, note = -h.bet, "lose"
            else:
                result, note = 0.0, "push"
            s.net += result
            s.log.append(f"You:    {show(h.cards)}  {note} {result:+g}")
        self._end_round(s)

    def _end_round(self, s: BJState) -> None:
        self._reveal_hole(s)
        s.prev_log = [f"Hand {s.round_no + 1}:"] + [f"  {line}" for line in s.log]
        s.round_no += 1
        if s.round_no >= s.rounds:
            s.stage = "done"
        else:
            self._start_round(s)

    # --- the contract ----------------------------------------------------------

    def legal_actions(self, s: BJState) -> list[str]:
        return [] if self.is_terminal(s) else ["next"]

    def apply(self, s: BJState, action: str) -> BJState:
        if action != "next" or self.is_terminal(s):
            raise ValueError(f"illegal action {action!r}")
        if s.stage == "drill":
            s.drill_pos += s.batch
            s.drill_tc = self._random_tc()
            if s.drill_pos >= len(s.drill_cards):
                s.stage = "done"
        elif s.stage == "bet":
            self._deal(s)
        elif s.stage == "insurance":
            s.insured = s.pending == "take"
            self._peek(s)
        elif s.stage == "decide":
            self._apply_decision(s, s.pending)
        s.pending = None
        return s

    def is_terminal(self, s: BJState) -> bool:
        return s.stage == "done"

    def result(self, s: BJState) -> float:
        """Net units won (drill: number of right counts)."""
        return float(s.count_right) if s.mode == "drill" else s.net

    # --- questions -------------------------------------------------------------

    def questions(self, s: BJState) -> list[Question]:
        if s.stage == "drill":
            return self._drill_questions(s)
        if s.stage == "bet":
            return self._bet_questions(s)
        if s.stage == "insurance":
            return [
                Question(
                    id=f"r{s.round_no}-ins",
                    kind=Kind.DECISION,
                    prompt=(
                        "Dealer shows an ace. Insurance? It costs half your bet and pays 2:1 "
                        "if the dealer has blackjack."
                    ),
                    category="insurance",
                    choices=("take", "decline"),
                    params={"keys": {"t": "take", "d": "decline"}},
                    tip="Insurance wins only if the hole card is a ten: worth it when more "
                    "than 1 in 3 unseen cards are tens (true count about +3).",
                )
            ]
        hand = s.hands[s.active]
        qs = []
        t, soft = total(hand.cards)
        if (
            s.bust_questions
            and len(hand.cards) == 2
            and not soft
            and 12 <= t <= 16
            and not hand.split
        ):
            qs.append(
                Question(
                    id=f"r{s.round_no}-bust",
                    kind=Kind.POINT,
                    prompt=f"You have {show(hand.cards)}. Chance you bust if you hit?",
                    category="bust-chance",
                    tolerance=0.03,
                    tip=f"You bust on any card worth {22 - t} or more.",
                )
            )
        evs = self.evs(s, hand)
        choices = tuple(a for a in ACTIONS if a in evs)
        kind = "pair" if self.situation(s, hand).pair else ("soft" if soft else "hard")
        qs.append(
            Question(
                id=f"r{s.round_no}-h{s.active}-c{len(hand.cards)}",
                kind=Kind.DECISION,
                prompt=f"Dealer shows {label(s.dealer[0])}. You have {show(hand.cards)}.",
                category=f"decision-{kind}",
                choices=choices,
                params={"keys": {k: v for k, v in KEYS.items() if v in choices}},
                tip="Stand on 12-16 against a weak dealer card (2-6), hit them against 7-A; "
                "always split aces and eights.",
            )
        )
        return qs

    def _bet_questions(self, s: BJState) -> list[Question]:
        return [
            Question(
                id=f"r{s.round_no}-rc",
                kind=Kind.POINT,
                prompt="Running count?",
                category="running-count",
                tip="+1 for 2-6, 0 for 7-9, −1 for tens and aces. Cancel pairs as you go.",
            ),
            Question(
                id=f"r{s.round_no}-tc",
                kind=Kind.POINT,
                prompt=f"True count? ({s.shoe.remaining} cards left in the shoe)",
                category="true-count",
                tolerance=0.5,
                tip="Divide the running count by the decks left (cards left / 52).",
            ),
            Question(
                id=f"r{s.round_no}-bet",
                kind=Kind.POINT,
                prompt="Your bet, in units (1-8)?",
                category="bet-spread",
                params={"min": 1, "max": 8},
                tip="Floor of the true count: ≤1 → 1, 2 → 2, 3 → 4, 4 → 6, 5+ → 8.",
            ),
        ]

    def _drill_questions(self, s: BJState) -> list[Question]:
        batch = s.drill_cards[s.drill_pos : s.drill_pos + s.batch]
        qs = [
            Question(
                id=f"d{s.drill_pos}",
                kind=Kind.SPEED,
                prompt=f"Cards: {'  '.join(label(c) for c in batch)}   Running count?",
                category="count-drill",
                target_seconds=1.0 + 0.75 * len(batch),
                params={"batch": batch},
                tip="Spot pairs that cancel (a 5 and a K) and count only what is left.",
            )
        ]
        if s.drill_pos % (3 * s.batch) == 2 * s.batch:
            rc, decks = s.drill_tc
            qs.append(
                Question(
                    id=f"tc{s.drill_pos}",
                    kind=Kind.SPEED,
                    prompt=f"Running count {rc:+d}, {decks:g} decks left. True count?",
                    category="true-count-drill",
                    tolerance=0.25,
                    target_seconds=6.0,
                    params={"rc": rc, "decks": decks},
                    tip="Halve twice for 4 decks, and so on; round to the nearest half.",
                )
            )
        return qs

    def truth(self, s: BJState, q: Question) -> Any:
        c = q.category
        if c.startswith("decision-"):
            return self.evs(s, s.hands[s.active])
        if c == "insurance":
            p = self.p_ten(s)
            return {"take": 0.5 * (3 * p - 1), "decline": 0.0}
        if c == "bust-chance":
            hand = s.hands[s.active]
            t, _ = total(hand.cards)
            comp = self.comp(s, hand)
            return sum(comp[v - 1] for v in range(1, 11) if t + v > 21)
        if c == "running-count":
            return float(self.running_count(s))
        if c == "true-count":
            return self.true_count(s)
        if c == "bet-spread":
            return float(hilo.bet_units(self.true_count(s)))
        if c == "count-drill":
            end = s.drill_pos + s.batch
            return float(hilo.running_count(s.drill_cards[:end]))
        if c == "true-count-drill":
            return q.params["rc"] / q.params["decks"]
        raise ValueError(f"unknown question {q.id}")

    def explain(self, s: BJState, q: Question) -> str:
        c = q.category
        if c.startswith("decision-"):
            return self._explain_decision(s)
        if c == "insurance":
            p = self.p_ten(s)
            return (
                f"P(hole card is a ten) = {p:.3f}. EV(take) = 0.5 × (2p − (1 − p)) = "
                f"{0.5 * (3 * p - 1):+.3f} per unit. Take it only when p > 1/3"
                + (f" (true count now {self.true_count(s):+.1f})." if s.mode == "count" else ".")
            )
        if c == "bust-chance":
            hand = s.hands[s.active]
            t, _ = total(hand.cards)
            return (
                f"Any card worth {22 - t} or more busts {t}: "
                f"{self.truth(s, q):.3f} of the unseen cards."
            )
        if c == "running-count":
            if s.shuffled:
                return "The shoe was just shuffled, so the count starts again at 0."
            parts = " ".join(f"{label(x)}({HILO[x]:+d})" for x in s.last_round)
            return f"Last round: {parts or 'no cards'}. Running count {self.running_count(s):+d}."
        if c == "true-count":
            left = sum(self.unseen_counts(s))
            return (
                f"{self.running_count(s):+d} / ({left} / 52 = {left / 52:.2f} decks) = "
                f"{self.true_count(s):+.2f}."
            )
        if c == "bet-spread":
            tc = self.true_count(s)
            return f"True count {tc:+.2f}, floor {int(tc // 1):+d} → {hilo.bet_units(tc)} unit(s)."
        if c == "count-drill":
            batch = q.params["batch"]
            parts = " ".join(f"{label(x)}({HILO[x]:+d})" for x in batch)
            change = sum(HILO[x] for x in batch)
            return f"{parts} = {change:+d}, running count {self.truth(s, q):+g}."
        if c == "true-count-drill":
            return f"{q.params['rc']:+d} / {q.params['decks']:g} = {self.truth(s, q):+.2f}."
        raise ValueError(f"unknown question {q.id}")

    def _explain_decision(self, s: BJState) -> str:
        hand = s.hands[s.active]
        evs = self.evs(s, hand)
        best = max(evs, key=lambda a: evs[a])
        text = "EV: " + ", ".join(f"{a} {evs[a]:+.3f}" for a in ACTIONS if a in evs)
        text += f". Best: {best}."
        key = self._chart_key(hand)
        if key and len(hand.cards) == 2 and not hand.split:
            code = chart(s.rules)[key][VALUE[s.dealer[0]]]
            text += f" Basic strategy chart: {code}."
        if s.mode == "count" and key:
            tc = self.true_count(s)
            for d in hilo.deviations_for(key, VALUE[s.dealer[0]]):
                play = d.at_or_above if tc >= d.index else d.below
                text += (
                    f" Count play ({d.group}) {d.name}: {d.at_or_above} at TC ≥ {d.index:+d}; "
                    f"TC now {tc:+.1f} → {play}."
                )
        return text

    @staticmethod
    def _chart_key(hand: Hand) -> str | None:
        values = [VALUE[c] for c in hand.cards]
        t, soft = total(hand.cards)
        if len(values) == 2 and values[0] == values[1]:
            return "pair " + (
                "AA" if values[0] == 1 else ("TT" if values[0] == 10 else str(values[0]) * 2)
            )
        if soft and 13 <= t <= 20:
            return f"soft A{t - 11}"
        if not soft and 5 <= t <= 20:
            return f"hard {t}"
        return None

    def observe(
        self, s: BJState, q: Question, answer: Any, score: Score, seconds: float
    ) -> BJState:
        s.asked_this_round += 1
        c = q.category
        if c.startswith("decision-"):
            s.pending = answer
            s.decisions += 1
            s.right += bool(score.correct)
            s.ev_lost += score.error
            if score.error > 1e-9:
                hand = s.hands[s.active]
                evs = self.evs(s, hand)
                best = max(evs, key=lambda a: evs[a])
                s.mistakes.append(
                    (
                        score.error,
                        f"{show(hand.cards)} vs {label(s.dealer[0])}: "
                        f"{answer} instead of {best} (−{score.error:.3f})",
                    )
                )
        elif c == "insurance":
            s.pending = answer
            s.decisions += 1
            s.right += bool(score.correct)
            s.ev_lost += score.error
            if score.error > 1e-9:
                s.mistakes.append((score.error, f"insurance: {answer} (−{score.error:.3f})"))
        elif c == "bet-spread":
            s.base_bet = float(answer)
        if c in ("running-count", "true-count", "count-drill", "true-count-drill"):
            s.count_asked += 1
            s.count_right += bool(score.correct)
        return s

    # --- text ------------------------------------------------------------------

    def describe(self, s: BJState) -> str:
        if s.stage == "drill":
            end = min(s.drill_pos + s.batch, len(s.drill_cards))
            return f"Count drill: cards {s.drill_pos + 1}-{end} of {len(s.drill_cards)}."
        lines = []
        if s.asked_this_round == 0 and s.prev_log:
            lines += s.prev_log + [""]
        if s.asked_this_round == 0 and s.shuffled:
            lines.append("The shoe has been shuffled.")
        lines.append(
            f"Hand {s.round_no + 1} of {s.rounds} | net {s.net:+g} units | "
            f"{s.shoe.remaining} cards left"
        )
        if s.stage in ("decide", "insurance"):
            lines.append(f"  Dealer: {label(s.dealer[0])} ?")
            for i, h in enumerate(s.hands):
                mark = ">" if i == s.active and s.stage == "decide" else " "
                extra = f"  bet {h.bet:g}" if h.bet != 1 or len(s.hands) > 1 else ""
                lines.append(f"{mark} You:    {show(h.cards)}{extra}")
        return "\n".join(lines)

    def summary(self, s: BJState) -> str:
        if s.mode == "drill":
            return f"Count drill: {s.count_right} of {s.count_asked} right."
        lines = list(s.prev_log) + [""] if s.prev_log else []
        lines.append(f"{s.round_no} hands, net {s.net:+g} units ({s.rules.describe()}).")
        if s.decisions:
            per100 = 100 * s.ev_lost / max(s.round_no, 1)
            lines.append(
                f"Decisions: {s.right} of {s.decisions} best; EV lost {s.ev_lost:.3f} bets "
                f"({per100:.2f} per 100 hands)."
            )
        if s.count_asked:
            lines.append(f"Count questions: {s.count_right} of {s.count_asked} right.")
        worst = sorted(s.mistakes, key=lambda m: -m[0])[:3]
        if worst:
            lines.append("Most expensive mistakes:")
            lines += [f"  {text}" for _, text in worst]
        return "\n".join(lines)
