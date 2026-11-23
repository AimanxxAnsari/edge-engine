"""The predict -> reveal -> score -> log loop, independent of any interface.

`Session` runs a game one step at a time, so any front end can drive it: the terminal
(`run_session`, below) or a web server answering one request at a time.
"""

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


class Session:
    """One game, stepped through question by question.

    At each game state: the state's description becomes the screen, its questions are
    asked one at a time, immediate questions are scored and revealed as they are
    answered, then the game's action is taken and forecasts (questions about what
    happens next) are scored against the new state. After every scored answer the
    module's observe() may update the state, and may end the game.

    With `wheels` (training wheels) each question has an Aid, and the session is logged
    as '<module>:wheels' so it stays out of normal stats.
    """

    def __init__(
        self,
        module: GameModule,
        seed: int,
        config: Mapping[str, Any] | None = None,
        act: ActFn | None = None,
        store: Store | None = None,
        wheels: bool = False,
    ) -> None:
        self.module = module
        self.seed = seed
        self.config = dict(config or {})
        if wheels:
            self.config["wheels"] = True
        self.wheels = wheels
        self._act = act or _only_action
        self._store = store
        self.state = module.init(Rng(seed), self.config)
        log_name = f"{module.name}:wheels" if wheels else module.name
        session_id = store.start_session(log_name, seed, self.config) if store else None
        self.out = SessionResult(module=module.name, seed=seed, session_id=session_id)
        self.screen = ""
        self.screen_id = 0
        self._batch: list[Question] = []
        self._index = 0
        self._pending: list[tuple[Question, Any, float, bool]] = []
        self._finished = False
        self._closed = False
        self._enter_state()

    # --- reading the session --------------------------------------------------------------

    @property
    def done(self) -> bool:
        return self.question is None

    @property
    def question(self) -> Question | None:
        """The question waiting for an answer, or None when the game is over."""
        if self._finished or self._index >= len(self._batch):
            return None
        return self._batch[self._index]

    def aid(self) -> Aid | None:
        """Training wheels: the truth and lessons for the current question."""
        q = self.question
        if not self.wheels or q is None:
            return None
        module, state = self.module, self.state
        if q.kind is Kind.PROBABILITY:  # a forecast: never reveal the future
            truth, explanation = None, ""
        else:
            truth, explanation = module.truth(state, q), module.explain(state, q)

        def judge(answer: Any) -> tuple[Score | None, str]:
            score = score_answer(q, answer, truth, 0.0) if truth is not None else None
            return score, module.judge(state, q, answer)

        return Aid(truth, explanation, module.lesson(state, q), judge)

    # --- moving the session on ----------------------------------------------------------------

    def answer(self, answer: Any, seconds: float = 0.0, assisted: bool = False) -> list[Turn]:
        """Answer the current question; return the turns revealed as a result."""
        q = self.question
        if q is None:
            raise ValueError("the session is over")
        revealed: list[Turn] = []
        self._index += 1
        if q.kind is Kind.PROBABILITY:
            self._pending.append((q, answer, seconds, assisted))
        else:
            revealed.append(self._finish(q, answer, seconds, assisted))
        if self._index >= len(self._batch):
            revealed += self._next_state()
        return revealed

    def quit(self) -> None:
        """Stop early: forecasts still waiting for their outcome are dropped, unscored."""
        self.out.completed = False
        self._pending = []
        self._batch, self._index = [], 0
        self._finished = True

    def finish(self) -> SessionResult:
        """Close the logged session and return the result. Safe to call more than once."""
        if self._store is not None and self.out.session_id is not None and not self._closed:
            self._store.end_session(self.out.session_id)
        self._closed = True
        self.out.result = self.module.result(self.state)
        self.out.summary = self.module.summary(self.state)
        return self.out

    # --- internals ------------------------------------------------------------------------------

    def _finish(self, q: Question, answer: Any, seconds: float, assisted: bool) -> Turn:
        """Score, log and record one answer, then let the game observe it."""
        at_state = self.state
        truth = self.module.truth(at_state, q)
        score = score_answer(q, answer, truth, seconds)
        turn = Turn(q, answer, truth, seconds, score, self.module.explain(at_state, q), assisted)
        self.out.turns.append(turn)
        if self._store is not None and self.out.session_id is not None:
            self._store.log_answer(self.out.session_id, q, answer, truth, score, seconds, assisted)
        self.state = self.module.observe(at_state, q, answer, score, seconds)
        return turn

    def _enter_state(self) -> None:
        """Start a game state: new screen and its questions (or game over)."""
        self._batch, self._index = [], 0
        while not self.module.is_terminal(self.state):
            self.screen = self.module.describe(self.state)
            self.screen_id += 1
            self._batch = list(self.module.questions(self.state))
            if self._batch:
                return
            # A state with no questions: take the action straight away.
            self.state = self.module.apply(
                self.state, self._act(self.state, self.module.legal_actions(self.state))
            )
        self._finished = True

    def _next_state(self) -> list[Turn]:
        """All of a state's questions are answered: act, then score the forecasts."""
        revealed: list[Turn] = []
        if self.module.is_terminal(self.state):  # observe() may end the game (e.g. time is up)
            self._batch, self._index = [], 0
            self._finished = True
            return revealed
        actions = self.module.legal_actions(self.state)
        self.state = self.module.apply(self.state, self._act(self.state, actions))
        pending, self._pending = self._pending, []
        for q, answer, seconds, assisted in pending:
            revealed.append(self._finish(q, answer, seconds, assisted))
        self._enter_state()
        return revealed


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
    """Play a whole session through ask / reveal / show callbacks (the terminal's way)."""
    session = Session(module, seed, config, act=act, store=store, wheels=wheels)
    shown = 0
    try:
        while not session.done:
            if show is not None and session.screen_id != shown:
                shown = session.screen_id
                if session.screen:
                    show(session.screen)
            q = session.question
            got = ask(q, aid=session.aid()) if wheels else ask(q)
            answer, seconds = got[0], got[1]
            assisted = bool(got[2]) if len(got) > 2 else False
            for turn in session.answer(answer, seconds, assisted):
                if reveal is not None:
                    reveal(turn)
    except Quit:
        session.quit()
    finally:
        result = session.finish()
    return result
