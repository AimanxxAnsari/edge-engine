"""Mental Maths Speed: sprint, 80-in-8 test and untimed practice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ...core import GameModule, Kind, Question
from ...rng import Rng
from ...scoring import Score
from ...storage import CategoryStats
from . import adaptive
from .questions import CATEGORIES, explain, make_params, prompt, solve, tolerance

MODES: dict[str, dict[str, Any]] = {
    "sprint": {"seconds": 120.0, "questions": None},
    "test": {"seconds": 480.0, "questions": 80},
    "practice": {"seconds": None, "questions": 20},
}


@dataclass(frozen=True)
class MentalState:
    mode: str
    seconds: float | None  # time limit (answering time only), None = untimed
    max_questions: int | None
    categories: tuple[str, ...]
    adaptive: bool
    params: dict[str, Any]  # the current question
    index: int = 0  # questions answered so far
    elapsed: float = 0.0
    correct: int = 0
    wrong: int = 0
    skipped: int = 0
    late: bool = False  # the last answer came after time ran out
    stats: dict[str, adaptive.CatStats] = field(default_factory=dict)


def _parse_categories(value: Any) -> tuple[str, ...]:
    if value is None:
        return tuple(CATEGORIES)
    names = value.split(",") if isinstance(value, str) else list(value)
    names = [n.strip() for n in names if n.strip()]
    unknown = [n for n in names if n not in CATEGORIES]
    if unknown or not names:
        known = ", ".join(CATEGORIES)
        raise ValueError(f"unknown categories {unknown}; known: {known}")
    return tuple(dict.fromkeys(names))


class MentalMaths(GameModule):
    name = "mental"
    title = "Mental Maths Speed"

    def __init__(self) -> None:
        self.history: dict[str, adaptive.CatStats] = {}

    # --- setup -------------------------------------------------------------

    def load_history(self, stats: list[CategoryStats]) -> None:
        self.history = {
            s.category: adaptive.from_history(s.n, s.accuracy, s.mean_seconds)
            for s in stats
            if s.category in CATEGORIES
        }

    def init(self, rng: Rng, config: Mapping[str, Any]) -> MentalState:
        mode = str(config.get("mode", "sprint"))
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
        defaults = MODES[mode]
        seconds = config.get("seconds", defaults["seconds"])
        questions = config.get("questions", defaults["questions"])
        if seconds is not None and float(seconds) <= 0:
            raise ValueError("seconds must be positive")
        if questions is not None and int(questions) < 1:
            raise ValueError("questions must be at least 1")
        self.rng = rng
        state = MentalState(
            mode=mode,
            seconds=None if seconds is None else float(seconds),
            max_questions=None if questions is None else int(questions),
            categories=_parse_categories(config.get("categories")),
            adaptive=bool(config.get("adaptive", True)),
            params={},
            stats=dict(self.history),
        )
        return replace(state, params=self._draw(state))

    def _draw(self, state: MentalState) -> dict[str, Any]:
        targets = {c: CATEGORIES[c].target for c in state.categories}
        probs = adaptive.probabilities(state.categories, state.stats, targets, state.adaptive)
        category = state.categories[self.rng.weighted_index(probs)]
        return make_params(self.rng, category)

    # --- game --------------------------------------------------------------

    def legal_actions(self, state: MentalState) -> list[str]:
        return [] if self.is_terminal(state) else ["next"]

    def apply(self, state: MentalState, action: str) -> MentalState:
        if action != "next" or self.is_terminal(state):
            raise ValueError(f"illegal action {action!r}")
        return replace(state, params=self._draw(state))

    def is_terminal(self, state: MentalState) -> bool:
        if state.seconds is not None and state.elapsed >= state.seconds:
            return True
        return state.max_questions is not None and state.index >= state.max_questions

    def result(self, state: MentalState) -> float:
        """sprint / practice: correct answers. test: correct − wrong."""
        if state.mode == "test":
            return float(state.correct - state.wrong)
        return float(state.correct)

    # --- questions ---------------------------------------------------------

    def questions(self, state: MentalState) -> list[Question]:
        p = state.params
        cat = CATEGORIES[p["cat"]]
        return [
            Question(
                id=f"q{state.index}",
                kind=Kind.SPEED,
                prompt=prompt(p),
                category=cat.name,
                tolerance=tolerance(p, solve(p)),
                target_seconds=cat.target,
                params=p,
                tip=cat.tip,
                skippable=True,
            )
        ]

    def truth(self, state: MentalState, question: Question) -> float:
        return float(solve(question.params))

    def explain(self, state: MentalState, question: Question) -> str:
        return explain(dict(question.params))

    def observe(
        self, state: MentalState, question: Question, answer: Any, score: Score, seconds: float
    ) -> MentalState:
        elapsed = state.elapsed + seconds
        in_time = state.seconds is None or elapsed <= state.seconds
        stats = dict(state.stats)
        prev = stats.get(question.category, adaptive.CatStats())
        stats[question.category] = prev.add(score.correct is True, seconds)
        new = replace(state, index=state.index + 1, elapsed=elapsed, stats=stats, late=not in_time)
        if not in_time:
            return new
        if score.correct is None:
            return replace(new, skipped=state.skipped + 1)
        if score.correct:
            return replace(new, correct=state.correct + 1)
        return replace(new, wrong=state.wrong + 1)

    # --- text --------------------------------------------------------------

    def describe(self, state: MentalState) -> str:
        parts = []
        if state.seconds is not None:
            parts.append(f"{max(0.0, state.seconds - state.elapsed):.0f}s left")
        n = f"{state.index + 1}"
        if state.max_questions is not None:
            n += f"/{state.max_questions}"
        parts.append(f"question {n}")
        parts.append(f"score {self.result(state):g}")
        return f"[{state.mode}] " + " | ".join(parts)

    def summary(self, state: MentalState) -> str:
        lines = [
            f"{state.mode}: score {self.result(state):g} "
            f"({state.correct} right, {state.wrong} wrong, {state.skipped} skipped) "
            f"in {state.elapsed:.0f}s of answering time."
        ]
        if state.mode == "test":
            lines.append("Scoring: +1 right, −1 wrong, 0 skipped.")
        if state.late:
            lines.append("The last answer came after time ran out, so it was not counted.")
        return "\n".join(lines)
