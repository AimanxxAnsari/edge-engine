"""A Claude tutor for the games: explains the engines' exact numbers, never invents its own.

Optional: needs the `anthropic` package (`pip install -e ".[tutor]"`) and credentials
(ANTHROPIC_API_KEY, or an `ant auth login` profile). Without them every game works as before.

What Claude is sent:
- once per session (cached): the rules for the tutor and the game's public docs/ explainer;
- with each question: the position as shown on screen, the question, and
  - in training wheels: the exact answer, its explanation and the lesson;
  - in scored modes before you answer: nothing that gives the answer away;
  - after a reveal: what was revealed (your answer, the truth, the explanation).
Nothing from local-brain/ is ever read or sent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "claude-opus-5-5"
MAX_EXCHANGES = 12  # keep the conversation short: older exchanges are dropped
DOCS = Path(__file__).resolve().parents[2] / "docs"
DOC_FILES = {
    "dice": "phase-0-foundations.md",
    "mental": "phase-1-mental-maths.md",
    "kelly": "phase-2-kelly.md",
    "blackjack": "phase-3-blackjack.md",
    "market": "phase-4-market-making.md",
    "poker": "phase-5-poker.md",
    "backgammon": "phase-6-backgammon.md",
    "chess": "phase-7-chess.md",
}
# US dollars per million tokens: input, output, cache read, cache write (5-minute TTL).
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}

RULES = """You are the tutor inside Edge Engine, a terminal trainer for probability, \
bet sizing and game theory. The player is learning the game described below.

How to help:
- Every number you state must come from GAME DATA in the player's message (computed \
exactly by the game's own engines and solvers) or be simple arithmetic on those \
numbers. Never invent probabilities, EVs, counts or evaluations. If GAME DATA does not \
contain what is needed, say so and explain the method instead.
- If GAME DATA says the answer is HIDDEN, the player has not answered yet in a scored \
mode: give a hint that points at the method or the right question to ask yourself, but \
do not give the answer, do not work it out to the end, and do not say which choice is \
best. If they insist, say the answer appears as soon as they commit.
- Otherwise explain the reasoning behind the answer clearly and concretely.
- Engine evaluations marked as an engine's opinion (backgammon checker play, chess) \
are heuristic, not exact; say so when it matters.
- Be brief: a few short sentences or a short list, plain text for a terminal, no \
headings or tables. Use the player's numbers, not abstract examples."""


def _background(game: str) -> str:
    name = DOC_FILES.get(game)
    if not name or not (DOCS / name).exists():
        return ""
    return (DOCS / name).read_text()


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, u: Any) -> None:
        self.requests += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0

    def cost(self, model: str) -> float | None:
        if model not in PRICES:
            return None
        p_in, p_out, p_read, p_write = PRICES[model]
        return (
            self.input_tokens * p_in
            + self.output_tokens * p_out
            + self.cache_read * p_read
            + self.cache_write * p_write
        ) / 1_000_000


@dataclass
class Context:
    """What the tutor may know about the current question."""

    screen: str  # the position as shown to the player
    question: str
    choices: tuple[str, ...] = ()
    answer: str | None = None  # None: hidden (scored mode, before the player commits)
    explanation: str = ""
    lesson: str = ""
    revealed: list[str] = field(default_factory=list)  # recent reveals

    def render(self) -> str:
        parts = ["GAME DATA", "Screen:", self.screen.strip() or "(nothing shown)", ""]
        parts.append(f"Question: {self.question}")
        if self.choices:
            shown = ", ".join(self.choices[:40]) + (" ..." if len(self.choices) > 40 else "")
            parts.append(f"Choices: {shown}")
        if self.answer is None:
            parts.append("Answer: HIDDEN (scored mode, the player has not committed yet)")
        else:
            parts.append(f"Answer (exact, from the game's engine): {self.answer}")
            if self.explanation:
                parts.append(f"Explanation: {self.explanation}")
            if self.lesson:
                parts.append(f"Lesson: {self.lesson}")
        if self.revealed:
            parts.append("")
            parts.append("Recently revealed (the player has seen these):")
            parts += [f"- {r}" for r in self.revealed]
        return "\n".join(parts)


class TutorError(RuntimeError):
    """The tutor could not answer (missing package, credentials, network...)."""


class Tutor:
    def __init__(
        self,
        game: str,
        model: str = DEFAULT_MODEL,
        client: Any = None,
        effort: str = "low",
    ) -> None:
        self.game = game
        self.model = model
        self.effort = effort
        self.usage = Usage()
        self.history: list[dict[str, str]] = []
        self.revealed: list[str] = []
        system = RULES
        background = _background(game)
        if background:
            system += "\n\nGame background (the project's own explainer):\n\n" + background
        self.system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise TutorError(
                    'the tutor needs the anthropic package: pip install -e ".[tutor]"'
                ) from None
            self._client = anthropic.Anthropic()
        return self._client

    def note_reveal(self, text: str) -> None:
        self.revealed = (self.revealed + [text])[-3:]

    def ask(self, context: Context, user_text: str, write: Callable[[str], None]) -> str:
        """Stream an answer to `write`; return the full text."""
        context.revealed = list(self.revealed)
        content = f"{context.render()}\n\nPLAYER: {user_text}"
        messages = self.history + [{"role": "user", "content": content}]
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=4000,
                system=self.system,
                messages=messages,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                parts = []
                for text in stream.text_stream:
                    parts.append(text)
                    write(text)
                final = stream.get_final_message()
        except TutorError:
            raise
        except Exception as e:  # noqa: BLE001 - reported to the player, never fatal to the game
            raise TutorError(_describe_error(e)) from e
        self.usage.add(final.usage)
        if final.stop_reason == "refusal":
            raise TutorError("the tutor declined to answer that")
        reply = "".join(parts)
        self.history = (self.history + messages[-1:] + [{"role": "assistant", "content": reply}])[
            -2 * MAX_EXCHANGES :
        ]
        return reply

    def summary(self) -> str:
        if not self.usage.requests:
            return ""
        u = self.usage
        cost = u.cost(self.model)
        money = f", about ${cost:.3f}" if cost is not None else ""
        return (
            f"Tutor ({self.model}): {u.requests} question(s); tokens in {u.input_tokens:,} "
            f"(+{u.cache_read:,} cached), out {u.output_tokens:,}{money}."
        )


def _describe_error(e: Exception) -> str:
    """A short message for the player, without importing anthropic at module level."""
    name = type(e).__name__
    messages = {
        "AuthenticationError": "no valid credentials (set ANTHROPIC_API_KEY or `ant auth login`)",
        "PermissionDeniedError": "these credentials cannot use this model",
        "NotFoundError": "unknown model",
        "RateLimitError": "rate limited, try again in a moment",
        "APIConnectionError": "cannot reach the API (network?)",
        "APITimeoutError": "the API timed out",
    }
    return messages.get(name, f"{name}: {e}")
