"""A small TD-Gammon-style network: self-play temporal-difference learning, in numpy.

Input: Tesauro's encoding of the position after a play, from the side that just moved
(4 units per point per player, bar and borne-off counts): 196 numbers.
Output: the estimated chance that the side that just moved wins.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ...rng import Rng
from .board import Play, Position, legal_plays, result
from .board import start as start_position

N_INPUTS = 196
DEFAULT_PATH = Path.home() / ".edge_engine" / "td-backgammon.npz"


def features(pos: Position) -> np.ndarray:
    x = np.zeros(N_INPUTS)
    k = 0
    for side in (1, -1):
        for n in pos.points:
            c = n * side
            if c > 0:
                x[k] = 1.0
                x[k + 1] = float(c >= 2)
                x[k + 2] = float(c >= 3)
                x[k + 3] = (c - 3) / 2 if c > 3 else 0.0
            k += 4
    x[192] = pos.bar / 2
    x[193] = pos.opp_bar / 2
    x[194] = pos.off / 15
    x[195] = pos.opp_off / 15
    return x


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


class Network:
    def __init__(self, hidden: int = 40, seed: int = 0) -> None:
        rng = Rng(seed)
        self.w1 = np.array(
            [[rng.uniform(-0.1, 0.1) for _ in range(N_INPUTS)] for _ in range(hidden)]
        )
        self.b1 = np.zeros(hidden)
        self.w2 = np.array([rng.uniform(-0.1, 0.1) for _ in range(hidden)])
        self.b2 = 0.0
        self.games = 0

    def value_batch(self, xs: np.ndarray) -> np.ndarray:
        h = _sigmoid(xs @ self.w1.T + self.b1)
        return _sigmoid(h @ self.w2 + self.b2)

    def value(self, pos: Position) -> float:
        won = result(pos)
        if won:
            return 1.0
        return float(self.value_batch(features(pos)[None, :])[0])

    def gradient(self, x: np.ndarray) -> tuple[float, dict[str, np.ndarray | float]]:
        """Output and its gradient with respect to every parameter."""
        h = _sigmoid(self.w1 @ x + self.b1)
        y = float(_sigmoid(np.array(h @ self.w2 + self.b2)))
        dy = y * (1 - y)
        dh = dy * self.w2 * h * (1 - h)
        return y, {"w2": dy * h, "b2": dy, "w1": np.outer(dh, x), "b1": dh}

    def update(self, x: np.ndarray, target: float, alpha: float) -> float:
        """One TD step: move the output for x towards target. Returns the error before."""
        y, g = self.gradient(x)
        err = target - y
        self.w2 += alpha * err * g["w2"]
        self.b2 += alpha * err * g["b2"]
        self.w1 += alpha * err * g["w1"]
        self.b1 += alpha * err * g["b1"]
        return err

    def choose(self, pos: Position, roll: tuple[int, int]) -> Play | None:
        plays = legal_plays(pos, roll)
        if not plays or not plays[0].moves:
            return None
        for p in plays:
            if result(p.after):
                return p
        xs = np.stack([features(p.after) for p in plays])
        return plays[int(np.argmax(self.value_batch(xs)))]

    def save(self, path: Path = DEFAULT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, w1=self.w1, b1=self.b1, w2=self.w2, b2=self.b2, games=self.games)

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> Network:
        data = np.load(path)
        net = cls(hidden=data["w1"].shape[0])
        net.w1, net.b1, net.w2 = data["w1"], data["b1"], data["w2"]
        net.b2, net.games = float(data["b2"]), int(data["games"])
        return net


def train(net: Network, games: int, rng: Rng, alpha: float = 0.3) -> list[float]:
    """Self-play TD(0) on after-states. Returns the mean |TD error| per game."""
    errors = []
    for _ in range(games):
        pos = start_position()
        prev: list[np.ndarray | None] = [None, None]
        turn = 0
        total, count = 0.0, 0
        while True:
            roll = (rng.randint(1, 6), rng.randint(1, 6))
            play = net.choose(pos, roll)
            after = play.after if play else pos
            if result(after):
                if prev[turn] is not None:
                    total += abs(net.update(prev[turn], 1.0, alpha))
                if prev[1 - turn] is not None:
                    total += abs(net.update(prev[1 - turn], 0.0, alpha))
                count += 2
                break
            x = features(after)
            if prev[turn] is not None:
                target = float(net.value_batch(x[None, :])[0])
                total += abs(net.update(prev[turn], target, alpha))
                count += 1
            prev[turn] = x
            pos = after.flip()
            turn = 1 - turn
        net.games += 1
        errors.append(total / max(count, 1))
    return errors
