"""Coin Flip with an Edge: bet sizing against Kelly, on the same flips."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from . import kmath, sim

MODES = ("classic", "unknown")
FAN_RUNS = 1000


@dataclass(frozen=True)
class KellyState:
    mode: str
    p: float  # true chance of heads (hidden in unknown mode)
    prior: tuple[int, int]  # Beta prior, unknown mode
    flips: int  # total flips
    start_c: int  # starting bankroll, cents
    cap_c: int | None  # winnings cap, cents
    wealth_c: int  # your bankroll, cents
    flip: int = 0  # flips done
    heads: int = 0
    tails: int = 0
    bet_c: int | None = None  # the bet placed for the next flip (+ heads, − tails)
    fractions: tuple[float, ...] = ()  # your bets as signed fractions of bankroll
    shadows: dict[str, int] = field(default_factory=dict)  # strategy -> bankroll, cents
    last: str = ""  # what happened on the last flip


def dollars(cents: float) -> str:
    sign = "−" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def growth_text(g: float) -> str:
    if g == -math.inf:
        return "−∞ (one loss wipes you out)"
    return f"{g:+.4f}".replace("-", "−")


def pct(f: float) -> str:
    """Signed percentage: +20% (heads), −19% (tails)."""
    return f"{f:+.0%}".replace("-", "−")


class CoinFlip(GameModule):
    name = "kelly"
    title = "Coin Flip with an Edge"

    # --- setup -------------------------------------------------------------

    def init(self, rng: Rng, config: Mapping[str, Any]) -> KellyState:
        mode = str(config.get("mode", "classic"))
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
        flips = int(config.get("flips", 50))
        start_c = round(float(config.get("start", 25)) * 100)
        cap = config.get("cap")
        cap_c = None if cap in (None, "none") else round(float(cap) * 100)
        prior = (int(config.get("prior_a", 5)), int(config.get("prior_b", 5)))
        if flips < 1 or start_c < 1:
            raise ValueError("need flips >= 1 and a positive start")
        if cap_c is not None and cap_c <= start_c:
            raise ValueError("the cap must be above the starting bankroll")
        self.rng = rng
        if mode == "classic":
            p = float(config.get("p", 0.6))
            if not 0 < p < 1:
                raise ValueError("p must be between 0 and 1")
        else:
            p = kmath.sample_beta(rng, *prior)
        state = KellyState(
            mode=mode,
            p=p,
            prior=prior,
            flips=flips,
            start_c=start_c,
            cap_c=cap_c,
            wealth_c=start_c,
        )
        return replace(state, shadows={name: start_c for name in self._strategies(state)})

    # --- the truth: Kelly bets ---------------------------------------------

    def believed_p(self, state: KellyState) -> float:
        """The chance of heads a perfect player would use right now."""
        if state.mode == "classic":
            return state.p
        return kmath.posterior_mean(*state.prior, state.heads, state.tails)

    def _strategies(self, state: KellyState) -> dict[str, Callable[[KellyState], float]]:
        """Shadow strategies: name -> signed bet fraction given the state."""

        def bayes(s: KellyState) -> float:
            return kmath.kelly_fraction(self.believed_p(s))

        if state.mode == "classic":
            return {
                "Kelly": bayes,
                "half Kelly": lambda s: bayes(s) / 2,
                "double Kelly": lambda s: max(-1.0, min(1.0, 2 * bayes(s))),
            }
        return {
            "Bayes-Kelly": bayes,
            "Bayes half-Kelly": lambda s: bayes(s) / 2,
            "oracle Kelly (knows p)": lambda s: kmath.kelly_fraction(s.p),
        }

    def _bet_cents(self, state: KellyState, wealth_c: int, f: float) -> int:
        """Signed bet in cents for fraction f, never more than needed to reach the cap."""
        bet = round(f * wealth_c)
        bet = max(-wealth_c, min(wealth_c, bet))
        if state.cap_c is not None:
            room = max(0, state.cap_c - wealth_c)
            bet = max(-room, min(room, bet))
        return bet

    def kelly_bet_c(self, state: KellyState) -> int:
        f = kmath.kelly_fraction(self.believed_p(state))
        return self._bet_cents(state, state.wealth_c, f)

    # --- game --------------------------------------------------------------

    def legal_actions(self, state: KellyState) -> list[str]:
        return [] if self.is_terminal(state) else ["flip"]

    def apply(self, state: KellyState, action: str) -> KellyState:
        if action != "flip" or self.is_terminal(state):
            raise ValueError(f"illegal action {action!r}")
        bet = state.bet_c or 0
        heads = self.rng.random() < state.p
        sign = 1 if heads else -1

        def settle(w: int, b: int) -> int:
            w += sign * b
            return min(w, state.cap_c) if state.cap_c is not None else w

        shadows = {
            name: settle(
                state.shadows[name], self._bet_cents(state, state.shadows[name], fn(state))
            )
            for name, fn in self._strategies(state).items()
        }
        wealth = settle(state.wealth_c, bet)
        side = "heads" if bet >= 0 else "tails"
        won = (bet >= 0) == heads
        if bet == 0:
            outcome = "you had no bet on"
        else:
            outcome = f"your {dollars(abs(bet))} on {side} {'won' if won else 'lost'}"
        last = f"Flip {state.flip + 1}: {'HEADS' if heads else 'TAILS'}, {outcome}."
        if state.wealth_c > 0 and bet != 0:
            f_user = bet / state.wealth_c
            pb = self.believed_p(state)
            f_k = kmath.kelly_fraction(pb)
            last += (
                f" You bet {pct(f_user)} of your bankroll; growth rate "
                f"{growth_text(kmath.growth_rate(f_user, pb))} against Kelly's "
                f"{growth_text(kmath.growth_rate(f_k, pb))} at {pct(f_k)}."
            )
        return replace(
            state,
            flip=state.flip + 1,
            heads=state.heads + heads,
            tails=state.tails + (not heads),
            wealth_c=wealth,
            bet_c=None,
            shadows=shadows,
            last=last,
        )

    def is_terminal(self, state: KellyState) -> bool:
        if state.flip >= state.flips or state.wealth_c < 1:
            return True
        return state.cap_c is not None and state.wealth_c >= state.cap_c

    def result(self, state: KellyState) -> float:
        """Final bankroll in dollars."""
        return state.wealth_c / 100

    # --- questions ---------------------------------------------------------

    def questions(self, state: KellyState) -> list[Question]:
        qs: list[Question] = []
        if state.flip == 0 and state.mode == "classic":
            qs += self._opening(state)
        if state.mode == "unknown" and state.flip > 0 and state.flip % 10 == 0:
            qs.append(
                Question(
                    id=f"est{state.flip}",
                    kind=Kind.POINT,
                    prompt=(
                        f"After {state.heads} heads and {state.tails} tails, "
                        "what is your estimate of P(heads)?"
                    ),
                    category="bias-estimate",
                    tolerance=0.03,
                    tip="Add the prior's pseudo-counts: (a + heads) / (a + b + flips).",
                )
            )
        w = state.wealth_c / 100
        qs.append(
            Question(
                id=f"bet{state.flip}",
                kind=Kind.POINT,
                prompt=f"Your bet? (bankroll {dollars(state.wealth_c)})",
                category="kelly-bet",
                tolerance=0.05 * w,
                params={"min": -w, "max": w, "pct_base": w, "unit": "dollars"},
                tip="Bet the edge: f* = 2p − 1 of your current bankroll, on the likelier side.",
            )
        )
        return qs

    def _opening(self, state: KellyState) -> list[Question]:
        start = dollars(state.start_c)
        return [
            Question(
                id="open-kelly",
                kind=Kind.POINT,
                prompt=(
                    f"The coin lands heads {state.p:.0%} of the time and bets pay even money. "
                    "What fraction of your bankroll should you bet each flip to grow it fastest?"
                ),
                category="kelly-fraction",
                tolerance=0.01,
                tip="Kelly: f* = (b·p − q)/b, which is 2p − 1 at even money.",
            ),
            Question(
                id="open-risk",
                kind=Kind.POINT,
                prompt=(
                    f"If you bet 30% of your bankroll on heads every flip for {state.flips} "
                    f"flips, what is the chance you finish below {start}?"
                ),
                category="kelly-risk",
                tolerance=0.05,
                tip="Final wealth depends only on the number of heads, which is binomial.",
            ),
        ]

    def truth(self, state: KellyState, question: Question) -> float:
        if question.category == "kelly-bet":
            return self.kelly_bet_c(state) / 100
        if question.category == "bias-estimate":
            return self.believed_p(state)
        if question.category == "kelly-fraction":
            return kmath.kelly_fraction(state.p)
        if question.category == "kelly-risk":
            return kmath.prob_below(1.0, 0.3, state.p, state.flips)
        raise ValueError(f"unknown question {question.id}")

    def explain(self, state: KellyState, question: Question) -> str:
        p = state.p
        if question.category == "kelly-fraction":
            return (
                f"Kelly: f* = 2p − 1 = 2({p:g}) − 1 = {kmath.kelly_fraction(p):.2f}. "
                f"Betting more grows slower, and above "
                f"{kmath.zero_growth_fraction(p):.0%} you shrink on average despite the edge."
            )
        if question.category == "kelly-risk":
            n = state.flips
            k_crit = n * math.log(1 / 0.7) / math.log(1.3 / 0.7)
            return (
                f"After k heads you have 1.3^k × 0.7^(n−k) of the start, which is below 1 "
                f"when k < {k_crit:.1f}. P(k < {k_crit:.1f}) for k ~ Binomial({n}, {p:g}) = "
                f"{kmath.prob_below(1.0, 0.3, p, n):.3f}, though the coin favours you."
            )
        if question.category == "bias-estimate":
            a, b = state.prior
            h, t = state.heads, state.tails
            raw = h / (h + t)
            return (
                f"Beta({a}, {b}) prior: as if you had already seen {a} heads and {b} tails. "
                f"Estimate = ({a} + {h}) / ({a + b} + {h + t}) = {self.believed_p(state):.3f}; "
                f"the raw share {raw:.3f} is pulled towards 0.5."
            )
        if question.category == "kelly-bet":
            pb = self.believed_p(state)
            f_k = kmath.kelly_fraction(pb)
            kelly = self.kelly_bet_c(state)
            side = "heads" if f_k >= 0 else "tails"
            if state.mode == "classic":
                text = f"Kelly: f* = 2p − 1 = {f_k:.2f}"
            else:
                a, b = state.prior
                text = (
                    f"Posterior Beta({a + state.heads}, {b + state.tails}), mean {pb:.3f}; "
                    f"Kelly with an uncertain bias uses the mean: f = 2m − 1 = {f_k:+.3f}"
                )
            text += (
                f", so bet {abs(f_k):.1%} of {dollars(state.wealth_c)} = "
                f"{dollars(abs(kelly))} on {side}."
            )
            if state.cap_c is not None and abs(kelly) < abs(round(f_k * state.wealth_c)):
                text += f" Capped: you only need {dollars(state.cap_c - state.wealth_c)} more."
            return text
        raise ValueError(f"unknown question {question.id}")

    def observe(
        self, state: KellyState, question: Question, answer: Any, score: Score, seconds: float
    ) -> KellyState:
        """Record the bet (in cents); the next 'flip' settles it."""
        if question.category != "kelly-bet":
            return state
        bet = round(float(answer or 0) * 100)
        bet = max(-state.wealth_c, min(state.wealth_c, bet))
        fraction = bet / state.wealth_c if state.wealth_c else 0.0
        return replace(state, bet_c=bet, fractions=state.fractions + (fraction,))

    # --- text --------------------------------------------------------------

    def describe(self, state: KellyState) -> str:
        lines = [state.last] if state.last else []
        if state.flip == 0:
            if state.mode == "classic":
                lines.append(
                    f"Bankroll {dollars(state.start_c)}. The coin lands heads {state.p:.0%} of "
                    f"the time; bets pay even money; {state.flips} flips."
                )
            else:
                a, b = state.prior
                lines.append(
                    f"Bankroll {dollars(state.start_c)}, {state.flips} flips, even money. "
                    f"The coin's bias is hidden: it was drawn from a Beta({a}, {b}) "
                    "distribution, centred on 50%."
                )
            if state.cap_c is not None:
                lines.append(f"Winnings are capped at {dollars(state.cap_c)}.")
            lines.append("Type a bet: 5 = $5 on heads, -5 = $5 on tails, 20% = 20% of bankroll.")
        head = f"Flip {state.flip + 1} of {state.flips} | bankroll {dollars(state.wealth_c)}"
        if state.mode == "unknown":
            head += f" | {state.heads} heads, {state.tails} tails so far"
        lines.append(head)
        return "\n".join(lines)

    def summary(self, state: KellyState) -> str:
        lines = [state.last, ""] if state.last else []
        lines.append(f"Final bankroll: you {dollars(state.wealth_c)}.")
        lines.append(
            "Same flips: " + " | ".join(f"{name} {dollars(w)}" for name, w in state.shadows.items())
        )
        n = state.heads + state.tails
        lines.append(f"Heads {state.heads} of {n}. The coin's bias was p = {state.p:.3f}.")
        if state.mode == "unknown" and n:
            lines.append(
                f"Your best estimate at the end would have been {self.believed_p(state):.3f}."
            )
        if state.cap_c is not None and state.wealth_c >= state.cap_c:
            lines.append(f"You reached the {dollars(state.cap_c)} cap after {state.flip} flips.")
        if state.wealth_c < 1:
            lines.append("You went broke.")
        lines += self._fan(state)
        return "\n".join(lines)

    @staticmethod
    def _best_growth(p: float) -> float:
        """Kelly's growth rate, betting on whichever side is favoured."""
        fav = max(p, 1 - p)
        return kmath.growth_rate(kmath.kelly_fraction(fav), fav)

    def _fan(self, state: KellyState) -> list[str]:
        if not state.fractions:
            return []
        avg = sum(state.fractions) / len(state.fractions)
        f, p = (avg, state.p) if avg >= 0 else (-avg, 1 - state.p)
        if f >= 1:
            return ["", "You bet everything: one loss ends the game, so there is no fan chart."]
        if f == 0:
            return []
        start = state.start_c / 100
        paths = sim.simulate_paths(self.rng, start, f, p, state.flips, FAN_RUNS)
        side = "heads" if avg >= 0 else "tails"
        return [
            "",
            f"{FAN_RUNS:,} simulated runs of {state.flips} flips at your average bet "
            f"({f:.1%} of bankroll on {side}; the cap is ignored here):",
            sim.fan_chart(paths),
            f"Chance of finishing below the start at that fraction: "
            f"{kmath.prob_below(1.0, f, p, state.flips):.3f} (exact). "
            f"Growth per flip {growth_text(kmath.growth_rate(f, p))}, "
            f"Kelly {growth_text(self._best_growth(state.p))}.",
        ]
