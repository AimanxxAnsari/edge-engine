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
    assisted: bool = False  # the tutor helped before the answer (scored modes)


@dataclass
class SessionResult:
    module: str
    seed: int
    session_id: int | None
    turns: list[Turn] = field(default_factory=list)
    result: float = 0.0
    completed: bool = True
    summary: str = ""

    @property
    def points(self) -> float:
        return sum(t.score.points for t in self.turns)

    @property
    def assisted(self) -> int:
        return sum(t.assisted for t in self.turns)


@dataclass(frozen=True)
class Aid:
    """What training wheels shows before and during a question."""

    truth: Any  # None for forecasts: their outcome isn't known yet
    explanation: str
    lesson: str
    judge: Callable[[Any], tuple[Score | None, str]]  # answer -> (would-be score, feedback)


# ask(question[, aid=Aid]) -> (answer, seconds) or (answer, seconds, assisted)
AskFn = Callable[..., tuple]
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
    wheels: bool = False,
) -> SessionResult:
    """Play one session.

    At each state: show the description, ask every question, score and reveal the
    immediate ones, take an action, then score the forecasts against the new state.
    After every scored answer the module's observe() may update the state.

    With `wheels` (training wheels), each question is asked with an Aid: the truth and
    explanation up front, and a judge for the answer before it counts. The session is
    logged as '<module>:wheels' so it stays out of normal stats.
    """
    config = dict(config or {})
    if wheels:
        config["wheels"] = True
    act = act or _only_action
    rng = Rng(seed)
    state = module.init(rng, config)
    log_name = f"{module.name}:wheels" if wheels else module.name
    session_id = store.start_session(log_name, seed, config) if store else None
    out = SessionResult(module=module.name, seed=seed, session_id=session_id)

    def finish(q: Question, answer: Any, seconds: float, at_state: Any, assisted: bool) -> Any:
        """Score, log and reveal one answer; return the state after module.observe."""
        truth = module.truth(at_state, q)
        score = score_answer(q, answer, truth, seconds)
        turn = Turn(q, answer, truth, seconds, score, module.explain(at_state, q), assisted)
        out.turns.append(turn)
        if store is not None and session_id is not None:
            store.log_answer(session_id, q, answer, truth, score, seconds, assisted)
        if reveal is not None:
            reveal(turn)
        return module.observe(at_state, q, answer, score, seconds)

    def make_aid(q: Question, at_state: Any) -> Aid:
        if q.kind is Kind.PROBABILITY:  # a forecast: never reveal the future
            truth, explanation = None, ""
        else:
            truth, explanation = module.truth(at_state, q), module.explain(at_state, q)

        def judge(answer: Any) -> tuple[Score | None, str]:
            score = score_answer(q, answer, truth, 0.0) if truth is not None else None
            return score, module.judge(at_state, q, answer)

        return Aid(truth, explanation, module.lesson(at_state, q), judge)

    try:
        while not module.is_terminal(state):
            if show is not None:
                text = module.describe(state)
                if text:
                    show(text)
            pending: list[tuple[Question, Any, float, bool]] = []
            for q in module.questions(state):
                got = ask(q, aid=make_aid(q, state)) if wheels else ask(q)
                answer, seconds = got[0], got[1]
                assisted = bool(got[2]) if len(got) > 2 else False
                if q.kind is Kind.PROBABILITY:
                    pending.append((q, answer, seconds, assisted))
                else:
                    state = finish(q, answer, seconds, state, assisted)
            if module.is_terminal(state):  # observe() may end the game (e.g. time is up)
                break
            state = module.apply(state, act(state, module.legal_actions(state)))
            for q, answer, seconds, assisted in pending:
                state = finish(q, answer, seconds, state, assisted)
    except Quit:
        out.completed = False  # forecasts still pending are dropped, unscored
    finally:
        if store is not None and session_id is not None:
            store.end_session(session_id)
    out.result = module.result(state)
    out.summary = module.summary(state)
    return out
