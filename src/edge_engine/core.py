"""Question types and the contract every game module follows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .rng import Rng

if TYPE_CHECKING:
    from .scoring import Score
    from .storage import CategoryStats


class Kind(str, Enum):
    POINT = "point"  # "what is your equity?" -> a number
    DECISION = "decision"  # "hit or stand?" -> one of the choices
    PROBABILITY = "probability"  # forecast of an event that resolves later (Brier)
    INTERVAL = "interval"  # "give a 90% range" -> (lo, hi)
    SPEED = "speed"  # exact answer, scored on time


@dataclass(frozen=True)
class Question:
    id: str
    kind: Kind
    prompt: str
    category: str
    tolerance: float = 0.0  # point / speed: allowed absolute error
    choices: tuple[str, ...] = ()  # decision
    level: float = 0.9  # interval: nominal coverage
    target_seconds: float | None = None  # speed: full points at or under this time
    params: Mapping[str, Any] = field(default_factory=dict)  # data the module needs later
    tip: str = ""  # general technique, shown after a wrong, skipped or slow answer
    skippable: bool = False  # the player may skip; the answer is then None

    def __post_init__(self) -> None:
        if self.kind is Kind.DECISION and len(self.choices) < 2:
            raise ValueError("a decision question needs at least two choices")
        if self.kind is Kind.SPEED and not self.target_seconds:
            raise ValueError("a speed question needs target_seconds")
        if self.kind is Kind.INTERVAL and not 0 < self.level < 1:
            raise ValueError("interval level must be in (0, 1)")


class GameModule(ABC):
    """A game plus the questions it asks.

    The state is whatever the game wants; the loop never looks inside it.
    Truth values:
      point / speed -> float
      decision      -> Mapping[choice, EV]
      probability   -> 0 or 1 (the outcome), read from the state after the next action
      interval      -> float
    """

    name: str = "module"
    title: str = "Module"

    @abstractmethod
    def init(self, rng: Rng, config: Mapping[str, Any]) -> Any: ...

    @abstractmethod
    def legal_actions(self, state: Any) -> list[str]: ...

    @abstractmethod
    def apply(self, state: Any, action: str) -> Any: ...

    @abstractmethod
    def is_terminal(self, state: Any) -> bool: ...

    @abstractmethod
    def result(self, state: Any) -> float: ...

    @abstractmethod
    def questions(self, state: Any) -> list[Question]: ...

    @abstractmethod
    def truth(self, state: Any, question: Question) -> Any: ...

    @abstractmethod
    def explain(self, state: Any, question: Question) -> str: ...

    # --- optional hooks (no-op defaults) ---------------------------------

    def describe(self, state: Any) -> str:
        """Text shown before the questions at each step."""
        return ""

    def observe(self, state: Any, question: Question, score: Score, seconds: float) -> Any:
        """Called after each answer is scored. Returns the (possibly updated) state."""
        return state

    def summary(self, state: Any) -> str:
        """Text shown when the session ends."""
        return ""

    def load_history(self, stats: list[CategoryStats]) -> None:
        """Receives this module's logged per-category stats before a session."""
        return None
