"""The predict -> reveal -> score -> log loop, independent of any interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .core import GameModule, Kind, Question
from .rng import Rng
from .scoring import Score, score_answer
from .storage import Store


class Quit(Exception):
    """Raised by an ask function to end the session early."""


@dataclass(frozen=True)
class Turn:
    question: Question
    answer: Any
    truth: Any
    seconds: float
    score: Score
    explanation: str


@dataclass
class SessionResult:
    module: str
    seed: int
    session_id: int | None
    turns: list[Turn] = field(default_factory=list)
    result: float = 0.0
    completed: bool = True

    @property
    def points(self) -> float:
        return sum(t.score.points for t in self.turns)


AskFn = Callable[[Question], tuple[Any, float]]  # returns (answer, seconds taken)
ActFn = Callable[[Any, list[str]], str]
RevealFn = Callable[[Turn], None]
ShowFn = Callable[[str], None]


def _only_action(state: Any, actions: list[str]) -> str:
    if len(actions) != 1:
        raise ValueError("several legal actions: pass an act function")
    return actions[0]


def run_session(
    module: GameModule,
    seed: int,
    ask: AskFn,
    config: Mapping[str, Any] | None = None,
    act: ActFn | None = None,
    reveal: RevealFn | None = None,
    show: ShowFn | None = None,
    store: Store | None = None,
) -> SessionResult:
    """Play one session.

    At each state: show the description, ask every question, score and reveal the
    immediate ones, take an action, then score the forecasts against the new state.
    """
    config = dict(config or {})
    act = act or _only_action
    rng = Rng(seed)
    state = module.init(rng, config)
    session_id = store.start_session(module.name, seed, config) if store else None
    out = SessionResult(module=module.name, seed=seed, session_id=session_id)

    def finish(q: Question, answer: Any, seconds: float, at_state: Any) -> None:
        truth = module.truth(at_state, q)
        score = score_answer(q, answer, truth, seconds)
        turn = Turn(q, answer, truth, seconds, score, module.explain(at_state, q))
        out.turns.append(turn)
        if store is not None and session_id is not None:
            store.log_answer(session_id, q, answer, truth, score, seconds)
        if reveal is not None:
            reveal(turn)

    try:
        while not module.is_terminal(state):
            if show is not None:
                text = module.describe(state)
                if text:
                    show(text)
            pending: list[tuple[Question, Any, float]] = []
            for q in module.questions(state):
                answer, seconds = ask(q)
                if q.kind is Kind.PROBABILITY:
                    pending.append((q, answer, seconds))
                else:
                    finish(q, answer, seconds, state)
            state = module.apply(state, act(state, module.legal_actions(state)))
            for q, answer, seconds in pending:
                finish(q, answer, seconds, state)
    except Quit:
        out.completed = False  # forecasts still pending are dropped, unscored
    finally:
        if store is not None and session_id is not None:
            store.end_session(session_id)
    out.result = module.result(state)
    return out
