"""Cards, hands, the shoe, the rules and the Hi-Lo count."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...rng import Rng

LABELS = "A23456789TJQK"
VALUE = {"A": 1, **{str(n): n for n in range(2, 10)}, "T": 10, "J": 10, "Q": 10, "K": 10}
HILO = {
    label: (1 if 2 <= VALUE[label] <= 6 else -1 if VALUE[label] in (1, 10) else 0)
    for label in LABELS
}
VALUES = tuple(range(1, 11))  # 1 = ace, 10 = any ten-value card


def hand_value(hard: int, ace: bool) -> tuple[int, bool]:
    """(best total, soft?) from the hard sum (aces as 1) and whether there is an ace."""
    if ace and hard + 10 <= 21:
        return hard + 10, True
    return hard, False


def total(cards: list[str]) -> tuple[int, bool]:
    hard = sum(VALUE[c] for c in cards)
    return hand_value(hard, any(c == "A" for c in cards))


def is_blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and total(cards)[0] == 21


def label(card: str) -> str:
    """How a card is shown: 'T' is shown as '10'."""
    return "10" if card == "T" else card


def show(cards: list[str]) -> str:
    """'A 7 (soft 18)'."""
    t, soft = total(cards)
    kind = "bust" if t > 21 else ("soft" if soft else "hard")
    return f"{' '.join(label(c) for c in cards)} ({kind} {t})"


@dataclass(frozen=True)
class Rules:
    decks: int = 6
    h17: bool = False  # dealer hits soft 17
    payout: float = 1.5  # blackjack pays 3:2 (1.5) or 6:5 (1.2)
    das: bool = True  # double after split
    surrender: bool = True  # late surrender
    resplit: bool = True  # resplit pairs other than aces
    penetration: float = 0.75  # share of the shoe dealt before a reshuffle

    def describe(self) -> str:
        return ", ".join(
            [
                f"{self.decks} decks",
                "H17" if self.h17 else "S17",
                "BJ pays 3:2" if self.payout == 1.5 else f"BJ pays {self.payout:g}:1",
                "DAS" if self.das else "no DAS",
                "late surrender" if self.surrender else "no surrender",
            ]
        )


@dataclass
class Shoe:
    """A shuffled shoe with a cut card. Cards are labels such as 'K' or '7'."""

    decks: int
    rng: Rng
    penetration: float = 0.75
    cards: list[str] = field(default_factory=list)
    pos: int = 0

    def __post_init__(self) -> None:
        self.shuffle()

    def shuffle(self) -> None:
        self.cards = list(LABELS) * 4 * self.decks
        self.rng.shuffle(self.cards)
        self.pos = 0

    def draw(self) -> str:
        card = self.cards[self.pos]
        self.pos += 1
        return card

    @property
    def remaining(self) -> int:
        return len(self.cards) - self.pos

    def needs_shuffle(self) -> bool:
        return self.pos >= self.penetration * len(self.cards)

    def counts(self) -> tuple[int, ...]:
        """Remaining cards by value 1..10 (index 0 = aces, index 9 = ten-values)."""
        out = [0] * 10
        for c in self.cards[self.pos :]:
            out[VALUE[c] - 1] += 1
        return tuple(out)

    def running_count(self) -> int:
        return sum(HILO[c] for c in self.cards[: self.pos])

    def decks_remaining(self) -> float:
        return self.remaining / 52

    def true_count(self) -> float:
        return self.running_count() / self.decks_remaining()
