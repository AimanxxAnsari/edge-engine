"""Expected-value solver: dealer outcomes, and the EV of every player action.

Cards are drawn independently from a fixed composition (the probability of each value
1..10). With the standard 1/13, 4/13 composition this is the classic infinite-deck
model; with the proportions of the cards left in a shoe it is the "current
composition" model used for count-dependent decisions.

The dealer peeks for blackjack (US rules), so all player decisions are evaluated given
that the dealer does not have blackjack.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache, lru_cache

from .cards import Rules, hand_value

Comp = tuple[float, ...]  # probabilities for values 1..10 (index 0 = ace)

INFINITE: Comp = tuple([1 / 13] * 9 + [4 / 13])
OUTCOMES = (17, 18, 19, 20, 21, 22)  # 22 = bust

ACTIONS = ("hit", "stand", "double", "split", "surrender")


def normalise(weights: Sequence[float]) -> Comp:
    total = sum(weights)
    if total <= 0 or len(weights) != 10:
        raise ValueError("need 10 non-negative weights with a positive sum")
    return tuple(w / total for w in weights)


def comp_from_counts(counts: Sequence[int]) -> Comp:
    """Proportions of the cards left in a shoe."""
    return normalise(counts)


def full_shoe(decks: int) -> list[int]:
    """Card counts by value for a full shoe: 4 of each value per deck, 16 ten-values."""
    return [4 * decks] * 9 + [16 * decks]


def comp_without(decks: int, removed: Sequence[int]) -> Comp:
    """Composition of a fresh shoe after removing known cards (values 1..10)."""
    counts = full_shoe(decks)
    for v in removed:
        if counts[v - 1] <= 0:
            raise ValueError("removed more cards than the shoe holds")
        counts[v - 1] -= 1
    return normalise(counts)


def comp_at_true_count(tc: float) -> Comp:
    """Average composition at a Hi-Lo true count.

    Per deck: 20 low cards (2-6), 12 neutral (7-9), 20 high (tens and aces). A true count
    of tc means high cards outnumber low cards by tc per deck, so there are 20 + tc/2
    high and 20 − tc/2 low cards per 52, each spread evenly within its group.
    """
    if not -40 < tc < 40:
        raise ValueError("true count out of range")
    low, high = (20 - tc / 2) / 5, (20 + tc / 2) / 20
    return normalise([4 * high] + [low] * 5 + [4.0] * 3 + [16 * high])


# --- dealer ------------------------------------------------------------------


def dealer_outcomes(up: int, comp: Comp, h17: bool, peek: bool = True) -> dict[int, float]:
    """Probability of each dealer final total (22 = bust) given the upcard.

    With peek, the hole card is drawn conditioned on the dealer not having blackjack.
    """
    return dict(zip(OUTCOMES, _dealer(up, comp, h17, peek), strict=True))


@lru_cache(maxsize=4096)
def _dealer(up: int, comp: Comp, h17: bool, peek: bool) -> tuple[float, ...]:
    @cache
    def go(hard: int, ace: bool) -> tuple[float, ...]:
        t, soft = hand_value(hard, ace)
        if t > 21:
            return (0, 0, 0, 0, 0, 1.0)
        if t >= 17 and not (t == 17 and soft and h17):
            out = [0.0] * 6
            out[t - 17] = 1.0
            return tuple(out)
        acc = [0.0] * 6
        for v in range(1, 11):
            p = comp[v - 1]
            if p:
                sub = go(hard + v, ace or v == 1)
                for i in range(6):
                    acc[i] += p * sub[i]
        return tuple(acc)

    # The hole card, possibly conditioned on "no blackjack".
    hole = list(comp)
    if peek and up == 1:
        hole[9] = 0.0
    elif peek and up == 10:
        hole[0] = 0.0
    total = sum(hole)
    acc = [0.0] * 6
    for v in range(1, 11):
        p = hole[v - 1] / total
        if p:
            sub = go(up + v, up == 1 or v == 1)
            for i in range(6):
                acc[i] += p * sub[i]
    return tuple(acc)


def dealer_blackjack_chance(up: int, comp: Comp) -> float:
    if up == 1:
        return comp[9]
    if up == 10:
        return comp[0]
    return 0.0


# --- player ------------------------------------------------------------------


@dataclass(frozen=True)
class Situation:
    """A player decision: hand (hard sum, has ace, cards), dealer upcard, and options."""

    hard: int
    ace: bool
    up: int
    pair: int | None = None  # value of the pair, if the hand is a splittable pair
    first: bool = True  # first decision on two cards (double / surrender allowed)
    split_hand: bool = False  # a hand created by splitting


class Solver:
    """EVs for one composition and rule set. All EVs are per unit of the original bet."""

    def __init__(self, comp: Comp, rules: Rules) -> None:
        self.comp = comp
        self.rules = rules
        self._cache: dict[tuple, float] = {}

    def dealer(self, up: int) -> dict[int, float]:
        return dealer_outcomes(up, self.comp, self.rules.h17)

    def stand(self, total: int, up: int) -> float:
        if total > 21:
            return -1.0
        d = _dealer(up, self.comp, self.rules.h17, True)
        ev = d[5]  # dealer busts
        for i, dt in enumerate(OUTCOMES[:5]):
            if total > dt:
                ev += d[i]
            elif total < dt:
                ev -= d[i]
        return ev

    def best_no_double(self, hard: int, ace: bool, up: int) -> float:
        """Best of hit and stand, playing on optimally (no double, no split)."""
        key = ("b", hard, ace, up)
        if key in self._cache:
            return self._cache[key]
        t, _ = hand_value(hard, ace)
        if t > 21:
            value = -1.0
        else:
            value = max(self.stand(t, up), self.hit(hard, ace, up))
        self._cache[key] = value
        return value

    def hit(self, hard: int, ace: bool, up: int) -> float:
        key = ("h", hard, ace, up)
        if key in self._cache:
            return self._cache[key]
        t, _ = hand_value(hard, ace)
        if t >= 21:
            value = -1.0 if t > 21 else self._hit_21(hard, ace, up)
        else:
            value = sum(
                p * self.best_no_double(hard + v, ace or v == 1, up)
                for v, p in zip(range(1, 11), self.comp, strict=True)
                if p
            )
        self._cache[key] = value
        return value

    def _hit_21(self, hard: int, ace: bool, up: int) -> float:
        # Hitting 21 is never right, but give it a value for completeness.
        return sum(
            p * self.best_no_double(hard + v, ace or v == 1, up)
            for v, p in zip(range(1, 11), self.comp, strict=True)
            if p
        )

    def double(self, hard: int, ace: bool, up: int) -> float:
        ev = 0.0
        for v, p in zip(range(1, 11), self.comp, strict=True):
            if p:
                t, _ = hand_value(hard + v, ace or v == 1)
                ev += p * self.stand(t, up)
        return 2 * ev

    def _split_hand_value(self, pair: int, second: int, up: int) -> float:
        """Best EV of one split hand holding (pair, second), without resplitting."""
        hard, ace = pair + second, pair == 1 or second == 1
        t, _ = hand_value(hard, ace)
        if pair == 1:  # split aces get one card each, and 21 is not a blackjack
            return self.stand(t, up)
        best = max(self.stand(t, up), self.hit(hard, ace, up))
        if self.rules.das:
            best = max(best, self.double(hard, ace, up))
        return best

    def split(self, pair: int, up: int) -> float:
        """EV of splitting, for both hands together.

        With resplitting (not aces), the per-hand value x solves x = A + p·max(B, 2x),
        where A covers non-matching second cards, B is a matching card kept as a pair,
        and p is the chance of a matching card. This is the unlimited-resplit
        approximation; casinos usually stop at four hands, which changes little.
        """
        key = ("p", pair, up)
        if key in self._cache:
            return self._cache[key]
        p_same = self.comp[pair - 1]
        a = sum(
            p * self._split_hand_value(pair, v, up)
            for v, p in zip(range(1, 11), self.comp, strict=True)
            if p and v != pair
        )
        b = self._split_hand_value(pair, pair, up)
        x = a + p_same * b
        if self.rules.resplit and pair != 1 and p_same < 0.5:
            x_resplit = a / (1 - 2 * p_same)
            if 2 * x_resplit >= b:
                x = max(x, x_resplit)
        self._cache[key] = 2 * x
        return 2 * x

    def evs(self, s: Situation) -> dict[str, float]:
        """EV of each legal action in this situation."""
        t, _ = hand_value(s.hard, s.ace)
        out = {"stand": self.stand(t, s.up), "hit": self.hit(s.hard, s.ace, s.up)}
        if s.first and (not s.split_hand or self.rules.das):
            out["double"] = self.double(s.hard, s.ace, s.up)
        if s.pair is not None and s.first:
            out["split"] = self.split(s.pair, s.up)
        if s.first and self.rules.surrender and not s.split_hand:
            out["surrender"] = -0.5
        return out

    def best(self, s: Situation) -> str:
        evs = self.evs(s)
        return max(evs, key=lambda a: (evs[a], -ACTIONS.index(a)))

    def round_ev(self) -> float:
        """Expected result of one round with perfect play: the player's edge."""
        c = self.comp
        ev = 0.0
        for up in range(1, 11):
            p_up = c[up - 1]
            p_dbj = dealer_blackjack_chance(up, c)
            for c1 in range(1, 11):
                for c2 in range(1, 11):
                    p = p_up * c[c1 - 1] * c[c2 - 1]
                    if not p:
                        continue
                    if {c1, c2} == {1, 10}:  # player blackjack
                        ev += p * (1 - p_dbj) * self.rules.payout
                        continue
                    pair = c1 if c1 == c2 else None
                    s = Situation(c1 + c2, 1 in (c1, c2), up, pair)
                    ev += p * (p_dbj * -1 + (1 - p_dbj) * max(self.evs(s).values()))
        return ev
