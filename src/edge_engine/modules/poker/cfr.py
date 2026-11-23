"""Counterfactual regret minimisation (CFR+) and best response for small poker games.

The tree is built over public betting histories. Each node stores numpy arrays over
every deal (the private cards, and the public card where there is one), so one pass
over the tree updates all deals at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


class Rules(Protocol):
    """What a game must provide to be built into a tree."""

    name: str

    def deals(self) -> list[tuple[tuple[int, ...], float]]: ...

    def actions(self, history: str) -> list[str]: ...  # [] when terminal

    def player(self, history: str) -> int: ...

    def payoff(self, history: str, deal: tuple[int, ...]) -> float: ...  # for player 0

    def infoset(self, player: int, history: str, deal: tuple[int, ...]) -> str: ...


@dataclass
class Node:
    history: str
    player: int = -1  # -1 at terminals
    actions: list[str] = field(default_factory=list)
    children: list[int] = field(default_factory=list)
    ids: np.ndarray | None = None  # info-set index per deal (decision nodes)
    payoff: np.ndarray | None = None  # player-0 payoff per deal (terminals)


class Tree:
    def __init__(self, rules: Rules) -> None:
        self.rules = rules
        deals = rules.deals()
        self.deals = [d for d, _ in deals]
        self.weights = np.array([w for _, w in deals], dtype=float)
        if not np.isclose(self.weights.sum(), 1.0):
            raise ValueError("deal weights must sum to 1")
        self.nodes: list[Node] = []
        self.index: dict[str, int] = {}
        self.infosets: list[str] = []
        self.infoset_index: dict[str, int] = {}
        self.infoset_actions: list[list[str]] = []
        self.infoset_player: list[int] = []
        self._build("")
        self.max_actions = max(len(a) for a in self.infoset_actions)

    def _build(self, history: str) -> int:
        idx = len(self.nodes)
        node = Node(history)
        self.nodes.append(node)
        self.index[history] = idx
        actions = self.rules.actions(history)
        if not actions:
            node.payoff = np.array([self.rules.payoff(history, d) for d in self.deals])
            return idx
        node.player = self.rules.player(history)
        node.actions = actions
        ids = []
        for d in self.deals:
            key = self.rules.infoset(node.player, history, d)
            if key not in self.infoset_index:
                self.infoset_index[key] = len(self.infosets)
                self.infosets.append(key)
                self.infoset_actions.append(actions)
                self.infoset_player.append(node.player)
            ids.append(self.infoset_index[key])
        node.ids = np.array(ids)
        child = getattr(self.rules, "child", lambda h, a: h + a)
        for a in actions:
            node.children.append(self._build(child(history, a)))
        return idx

    @property
    def decision_nodes(self) -> list[Node]:
        return [n for n in self.nodes if n.player >= 0]

    # --- strategies --------------------------------------------------------------

    def uniform(self) -> np.ndarray:
        s = np.zeros((len(self.infosets), self.max_actions))
        for i, acts in enumerate(self.infoset_actions):
            s[i, : len(acts)] = 1.0 / len(acts)
        return s

    def mask(self) -> np.ndarray:
        m = np.zeros((len(self.infosets), self.max_actions), dtype=bool)
        for i, acts in enumerate(self.infoset_actions):
            m[i, : len(acts)] = True
        return m

    # --- evaluation ----------------------------------------------------------------

    def forward(self, strategy: np.ndarray) -> tuple[list, list]:
        """Reach probabilities of both players at every node, per deal."""
        n = len(self.weights)
        reach = [None] * len(self.nodes)
        probs = [None] * len(self.nodes)
        reach[0] = (np.ones(n), np.ones(n))
        for idx, node in enumerate(self.nodes):  # parents come before children
            if node.player < 0:
                continue
            p = strategy[node.ids, : len(node.actions)]
            probs[idx] = p
            r0, r1 = reach[idx]
            for k, child in enumerate(node.children):
                if node.player == 0:
                    reach[child] = (r0 * p[:, k], r1)
                else:
                    reach[child] = (r0, r1 * p[:, k])
        return reach, probs

    def backward(self, probs: list) -> list[np.ndarray]:
        """Player-0 expected payoff at every node, per deal."""
        values: list = [None] * len(self.nodes)
        for idx in range(len(self.nodes) - 1, -1, -1):
            node = self.nodes[idx]
            if node.player < 0:
                values[idx] = node.payoff
            else:
                p = probs[idx]
                values[idx] = sum(p[:, k] * values[c] for k, c in enumerate(node.children))
        return values

    def value(self, strategy: np.ndarray) -> float:
        """Expected payoff to player 0 when both play `strategy`."""
        _, probs = self.forward(strategy)
        return float(np.dot(self.weights, self.backward(probs)[0]))

    def best_response(self, strategy: np.ndarray, player: int) -> tuple[float, np.ndarray]:
        """Best-response value for `player` against `strategy`, and per-info-set action values.

        The action values are counterfactual: for each of the player's info sets, the
        expected payoff of each action (then best-responding), averaged over the deals in
        the info set weighted by the opponent's reach and chance.
        """
        reach, probs = self.forward(strategy)
        sign = 1.0 if player == 0 else -1.0
        values: list = [None] * len(self.nodes)
        q = np.full((len(self.infosets), self.max_actions), np.nan)
        for idx in range(len(self.nodes) - 1, -1, -1):
            node = self.nodes[idx]
            if node.player < 0:
                values[idx] = sign * node.payoff
            elif node.player != player:
                p = probs[idx]
                values[idx] = sum(p[:, k] * values[c] for k, c in enumerate(node.children))
            else:
                w = reach[idx][1 - player] * self.weights
                size = len(self.infosets)
                totals = np.bincount(node.ids, weights=w, minlength=size)
                scores = np.stack(
                    [
                        np.bincount(node.ids, weights=w * values[c], minlength=size)
                        for c in node.children
                    ],
                    axis=1,
                )
                used = np.unique(node.ids)
                with np.errstate(invalid="ignore", divide="ignore"):
                    q[used, : len(node.children)] = scores[used] / totals[used, None]
                best = np.argmax(scores, axis=1)
                choice = best[node.ids]
                stacked = np.stack([values[c] for c in node.children], axis=1)
                values[idx] = stacked[np.arange(len(node.ids)), choice]
        return float(np.dot(self.weights, values[0])), q

    def exploitability(self, strategy: np.ndarray) -> float:
        """Average gain of a best responder over the equilibrium value; 0 at equilibrium."""
        b0, _ = self.best_response(strategy, 0)
        b1, _ = self.best_response(strategy, 1)
        return (b0 + b1) / 2


class CFRPlus:
    """CFR+ with alternating updates and linearly weighted strategy averaging."""

    def __init__(self, tree: Tree) -> None:
        self.tree = tree
        shape = (len(tree.infosets), tree.max_actions)
        self.regret = np.zeros(shape)
        self.strategy_sum = np.zeros(shape)
        self.mask = tree.mask()
        self.iterations = 0

    def current(self) -> np.ndarray:
        pos = np.where(self.mask, np.maximum(self.regret, 0.0), 0.0)
        totals = pos.sum(axis=1, keepdims=True)
        uniform = self.tree.uniform()
        with np.errstate(invalid="ignore", divide="ignore"):
            out = np.where(totals > 0, pos / totals, uniform)
        return out

    def average(self) -> np.ndarray:
        totals = self.strategy_sum.sum(axis=1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            out = np.where(totals > 0, self.strategy_sum / totals, self.tree.uniform())
        return out

    def iterate(self, n: int = 1) -> None:
        t = self.tree
        for _ in range(n):
            self.iterations += 1
            for player in (0, 1):
                strategy = self.current()
                reach, probs = t.forward(strategy)
                values = t.backward(probs)
                sign = 1.0 if player == 0 else -1.0
                for idx, node in enumerate(t.nodes):
                    if node.player != player:
                        continue
                    v_node = sign * values[idx]
                    w_opp = reach[idx][1 - player] * t.weights
                    w_own = reach[idx][player] * t.weights
                    p = probs[idx]
                    for k, child in enumerate(node.children):
                        gain = w_opp * (sign * values[child] - v_node)
                        np.add.at(self.regret[:, k], node.ids, gain)
                        np.add.at(
                            self.strategy_sum[:, k], node.ids, self.iterations * w_own * p[:, k]
                        )
                np.maximum(self.regret, 0.0, out=self.regret)

    def solve(self, iterations: int) -> np.ndarray:
        self.iterate(iterations)
        return self.average()
