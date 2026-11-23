"""Rules of Kuhn poker and Leduc Hold'em, in the form the CFR tree builder needs."""

from __future__ import annotations

RANK_NAMES = "JQK"


class Kuhn:
    """Kuhn poker: J < Q < K, ante 1, one round, bet 1. Actions: p (check/fold), b (bet/call)."""

    name = "kuhn"

    def deals(self) -> list[tuple[tuple[int, ...], float]]:
        return [((a, b), 1 / 6) for a in range(3) for b in range(3) if a != b]

    def actions(self, h: str) -> list[str]:
        if h in ("pp", "bp", "bb", "pbp", "pbb"):
            return []
        return ["p", "b"]

    def player(self, h: str) -> int:
        return len(h) % 2

    def payoff(self, h: str, deal: tuple[int, ...]) -> float:
        c0, c1 = deal
        win = 1.0 if c0 > c1 else -1.0
        if h == "pp":
            return win
        if h == "bp":
            return 1.0  # player 1 folds to the bet
        if h == "pbp":
            return -1.0  # player 0 folds
        return 2.0 * win  # bb, pbb: showdown for 2

    def infoset(self, player: int, h: str, deal: tuple[int, ...]) -> str:
        return f"{RANK_NAMES[deal[player]]}:{h}"


class Leduc:
    """Leduc Hold'em: J J Q Q K K; ante 1; bets 2 then 4; one bet and one raise per round.

    History: round-1 actions, '/', round-2 actions. c = check/call, r = bet/raise, f = fold.
    A deal is (card of player 0, card of player 1, public card), by rank.
    """

    name = "leduc"
    BET = (2, 4)
    MAX_RAISES = 2

    def deals(self) -> list[tuple[tuple[int, ...], float]]:
        out = []
        for a in range(3):
            for b in range(3):
                pb = (2 - (b == a)) / 5
                for c in range(3):
                    left = 2 - (c == a) - (c == b)
                    if left > 0:
                        out.append(((a, b, c), (1 / 3) * pb * left / 4))
        return out

    @staticmethod
    def _round_actions(seq: str) -> tuple[bool, list[str]]:
        """(round over?, legal actions) for one round's action string."""
        if seq.endswith("f"):
            return True, []
        if seq in ("cc",) or (seq.endswith("c") and "r" in seq):
            return True, []
        raises = seq.count("r")
        facing = seq.endswith("r")
        if facing:
            acts = ["f", "c"] + (["r"] if raises < Leduc.MAX_RAISES else [])
        else:
            acts = ["c", "r"]
        return False, acts

    def _norm(self, h: str) -> str:
        """Add the round separator once round 1 is over (the public card comes out)."""
        if "/" not in h and "f" not in h and self._round_actions(h)[0]:
            return h + "/"
        return h

    def child(self, h: str, a: str) -> str:
        return self._norm(h) + a

    def actions(self, h: str) -> list[str]:
        h = self._norm(h)
        if "f" in h:
            return []
        rounds = h.split("/")
        done, acts = self._round_actions(rounds[-1])
        return [] if done else acts

    def player(self, h: str) -> int:
        return len(self._norm(h).split("/")[-1]) % 2

    def contributions(self, h: str) -> list[int]:
        paid = [1, 1]
        for r, seq in enumerate(h.split("/")):
            outstanding = 0  # what the player to act must add to call
            for i, a in enumerate(seq):
                p = i % 2
                if a == "c":
                    paid[p] += outstanding
                    outstanding = 0
                elif a == "r":
                    paid[p] += outstanding + self.BET[r]
                    outstanding = self.BET[r]
        return paid

    def payoff(self, h: str, deal: tuple[int, ...]) -> float:
        paid = self.contributions(h)
        seq = h.split("/")[-1]
        if seq.endswith("f"):
            folder = (len(seq) - 1) % 2
            return -paid[0] if folder == 0 else paid[1]
        a, b, c = deal
        sa = (10 + a) if a == c else a
        sb = (10 + b) if b == c else b
        if sa == sb:
            return 0.0
        return paid[0] if sa > sb else -paid[0]

    def infoset(self, player: int, h: str, deal: tuple[int, ...]) -> str:
        card = RANK_NAMES[deal[player]]
        h = self._norm(h)
        if "/" in h:
            return f"{card}{RANK_NAMES[deal[2]]}:{h}"
        return f"{card}:{h}"
