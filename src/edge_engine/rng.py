"""Seeded random number generator: xoshiro256** seeded with SplitMix64.

Written from scratch so a seed gives the same game on every Python version.
Reference: Blackman & Vigna, "Scrambled linear pseudorandom number generators" (2018),
https://prng.di.unimi.it/
"""

from __future__ import annotations

from collections.abc import MutableSequence, Sequence
from typing import TypeVar

T = TypeVar("T")

MASK64 = (1 << 64) - 1


def _rotl(x: int, k: int) -> int:
    """Rotate a 64-bit word left by k bits."""
    return ((x << k) | (x >> (64 - k))) & MASK64


class SplitMix64:
    """Tiny 64-bit generator, used only to expand a seed into xoshiro's state."""

    def __init__(self, seed: int) -> None:
        self.state = seed & MASK64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)


class Rng:
    """xoshiro256** generator with the helpers the games need."""

    def __init__(self, seed: int = 0) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        self.seed = seed
        sm = SplitMix64(seed)
        self._s = [sm.next_u64() for _ in range(4)]

    # --- state -----------------------------------------------------------

    @classmethod
    def from_state(cls, state: Sequence[int]) -> Rng:
        """Build a generator directly from four 64-bit state words."""
        words = [int(w) & MASK64 for w in state]
        if len(words) != 4:
            raise ValueError("state must have four words")
        if not any(words):
            raise ValueError("state must not be all zeros")
        rng = cls.__new__(cls)
        rng.seed = -1
        rng._s = words
        return rng

    def getstate(self) -> tuple[int, int, int, int]:
        s0, s1, s2, s3 = self._s
        return (s0, s1, s2, s3)

    def setstate(self, state: Sequence[int]) -> None:
        self._s = list(Rng.from_state(state)._s)

    # --- core ------------------------------------------------------------

    def next_u64(self) -> int:
        """Next raw 64-bit output."""
        s0, s1, s2, s3 = self._s
        result = (_rotl((s1 * 5) & MASK64, 7) * 9) & MASK64
        t = (s1 << 17) & MASK64
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl(s3, 45)
        self._s = [s0, s1, s2, s3]
        return result

    def random(self) -> float:
        """Uniform float in [0, 1), using the top 53 bits."""
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def randbelow(self, n: int) -> int:
        """Uniform integer in [0, n), without modulo bias.

        Take the top `bits` bits, where 2**bits is the smallest power of two >= n,
        and reject values >= n. Each try succeeds with probability > 1/2.
        """
        if n <= 0:
            raise ValueError("n must be positive")
        if n > 1 << 64:
            raise ValueError("n must be at most 2**64")
        if n == 1:
            return 0
        bits = (n - 1).bit_length()
        while True:
            r = self.next_u64() >> (64 - bits)
            if r < n:
                return r

    # --- helpers ---------------------------------------------------------

    def randint(self, a: int, b: int) -> int:
        """Uniform integer in [a, b], both ends included."""
        if b < a:
            raise ValueError("empty range")
        return a + self.randbelow(b - a + 1)

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def bernoulli(self, p: float) -> bool:
        """True with probability p."""
        if not 0.0 <= p <= 1.0:
            raise ValueError("p must be in [0, 1]")
        return self.random() < p

    def weighted_index(self, weights: Sequence[float]) -> int:
        """Index i with probability weights[i] / sum(weights)."""
        if not weights or any(w < 0 for w in weights) or sum(weights) <= 0:
            raise ValueError("weights must be non-negative with a positive sum")
        x = self.random() * sum(weights)
        total = 0.0
        for i, w in enumerate(weights):
            total += w
            if x < total:
                return i
        return max(i for i, w in enumerate(weights) if w > 0)  # float round-off at the top

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise IndexError("cannot choose from an empty sequence")
        return seq[self.randbelow(len(seq))]

    def shuffle(self, items: MutableSequence[T]) -> None:
        """Fisher-Yates shuffle, in place."""
        for i in range(len(items) - 1, 0, -1):
            j = self.randbelow(i + 1)
            items[i], items[j] = items[j], items[i]

    def sample(self, seq: Sequence[T], k: int) -> list[T]:
        """k distinct items, in random order (partial Fisher-Yates)."""
        if not 0 <= k <= len(seq):
            raise ValueError("k must be between 0 and len(seq)")
        pool = list(seq)
        n = len(pool)
        for i in range(k):
            j = i + self.randbelow(n - i)
            pool[i], pool[j] = pool[j], pool[i]
        return pool[:k]
