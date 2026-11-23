"""Terminal front end: answer parsing, prompting and the reveal."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from fractions import Fraction
from typing import Any

from .core import Kind, Question
from .loop import Aid, Quit, Turn
from .tutor import Context, Tutor, TutorError

QUIT_WORDS = {"q", "quit", "exit"}
SKIP_WORDS = {"s", "skip"}

HINTS = {
    Kind.POINT: "a number: 0.25, 1/4 or 25%",
    Kind.SPEED: "a number",
    Kind.PROBABILITY: "a probability: 0.25, 1/4 or 25%",
    Kind.INTERVAL: "two numbers: low high",
}


class ParseError(ValueError):
    pass


def parse_number(text: str) -> float:
    """Accept '0.25', '1/4', '25%', '-3', '1e3'."""
    s = text.strip().replace(",", "").replace("−", "-")
    if not s:
        raise ParseError("empty answer")
    try:
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        if "/" in s:
            num, den = s.split("/", 1)
            return float(Fraction(int(num), int(den)))
        return float(s)
    except (ValueError, ZeroDivisionError):
        raise ParseError(f"not a number: {text!r}") from None


def parse_answer(question: Question, text: str) -> Any:
    """Parse typed text for this question. Returns None for a skip."""
    if question.skippable and text.strip().lower() in SKIP_WORDS:
        return None
    params = question.params
    if params.get("unit") == "percent":  # '25' and '25%' both mean 25
        return parse_number(text.strip().removesuffix("%"))
    if "pct_base" in params and text.strip().endswith("%"):  # '20%' of the base
        value = parse_number(text) * float(params["pct_base"])
        return _check_range(question, value)
    kind = question.kind
    if kind is Kind.DECISION:
        keys = params.get("keys", {})
        if text.strip() in keys:  # exact first: 'bxc3' and 'Bxc3' are different moves
            return keys[text.strip()]
        if text.strip() in question.choices:
            return text.strip()
        s = text.strip().lower()
        if s in keys:
            return keys[s]
        choices = [c.lower() for c in question.choices]
        if s.isdigit() and 1 <= int(s) <= len(choices):
            return question.choices[int(s) - 1]
        pairs = zip(question.choices, choices, strict=True)
        matches = [c for c, low in pairs if s and low.startswith(s)]
        if len(matches) == 1:
            return matches[0]
        if "hint" in params:
            raise ParseError(f"{text.strip()!r} is not one of the choices ({params['hint']})")
        if len(question.choices) > 6:
            raise ParseError(f"choose a number from 1 to {len(question.choices)}, or the moves")
        raise ParseError(f"choose one of: {', '.join(question.choices)}")
    if kind is Kind.INTERVAL:
        parts = [p for p in re.split(r"[\s;@]+|\bto\b", text.strip()) if p]
        if len(parts) != 2:
            raise ParseError("give two numbers: low high")
        lo, hi = parse_number(parts[0]), parse_number(parts[1])
        if hi < lo:
            raise ParseError("the low end must not be above the high end")
        width = params.get("max_width")
        if width is not None and hi - lo > float(width) + 1e-9:
            raise ParseError(f"at most {float(width):g} wide")
        if width is not None and hi == lo:
            raise ParseError("the bid must be below the ask")
        return (lo, hi)
    value = parse_number(text)
    if kind is Kind.PROBABILITY and not 0.0 <= value <= 1.0:
        raise ParseError("a probability must be between 0 and 1")
    return _check_range(question, value)


def _check_range(question: Question, value: float) -> float:
    lo, hi = question.params.get("min"), question.params.get("max")
    if lo is not None and value < lo - 1e-9 or hi is not None and value > hi + 1e-9:
        raise ParseError(f"must be between {_show(question, lo)} and {_show(question, hi)}")
    return value


def _show(question: Question, x: Any) -> str:
    if x is None:
        return "any"
    if question.params.get("unit") == "dollars":
        sign = "−" if x < 0 else ""
        return f"{sign}${abs(x):,.2f}"
    return _fmt(float(x))


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.4f}"


def format_truth(question: Question, truth: Any) -> str:
    kind = question.kind
    if kind is Kind.DECISION:
        best = max(truth, key=truth.get)
        if len(truth) > 6:
            return f"{best}  (EV {truth[best]:+.4f}, best of {len(truth)})"
        evs = ", ".join(f"{c} {v:+.4f}" for c, v in truth.items())
        return f"{best}  (EV: {evs})"
    if kind is Kind.PROBABILITY:
        return "it happened (1)" if truth else "it did not happen (0)"
    return _show(question, float(truth))


def format_answer(question: Question, answer: Any) -> str:
    if answer is None:
        return "skipped"
    if question.kind is Kind.INTERVAL:
        lo, hi = answer
        return f"[{_fmt(lo)}, {_fmt(hi)}]"
    if question.kind is Kind.DECISION:
        return str(answer)
    return _show(question, float(answer))


def show_tip(turn: Turn) -> bool:
    """Tips are shown after a wrong, skipped or slower-than-target answer."""
    target = turn.question.target_seconds
    return turn.score.correct is not True or (target is not None and turn.seconds > target)


class TerminalUI:
    """Reads answers and prints reveals. input/output/clock are injectable for tests."""

    def __init__(
        self,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
        tutor: Tutor | None = None,
        write: Callable[[str], None] | None = None,
    ) -> None:
        # Look up input/print at call time, so they can be swapped (e.g. in tests).
        self.input = input_fn or (lambda prompt: input(prompt))
        self.out = output_fn or (lambda text: print(text))
        self.write = write or (lambda text: print(text, end="", flush=True))
        self.clock = clock
        self.tutor = tutor
        self.screen = ""  # the last position shown, for the tutor

    def show(self, text: str) -> None:
        self.screen = text
        self.out("")
        self.out(text)

    def _help(self, question: Question, aid: Aid | None, text: str) -> bool:
        """Ask the tutor. Returns True if it answered."""
        if self.tutor is None:
            self.out("  (the tutor is off: add --tutor to use it)")
            return False
        answer = None
        explanation = lesson = ""
        if aid is not None and aid.truth is not None:
            answer = format_truth(question, aid.truth)
            explanation, lesson = aid.explanation, aid.lesson
        context = Context(
            screen=self.screen,
            question=question.prompt,
            choices=question.choices,
            answer=answer,
            explanation=explanation,
            lesson=lesson,
        )
        self.write("  tutor: ")
        try:
            self.tutor.ask(context, text or "Give me a hint.", self.write)
        except TutorError as e:
            self.out(f"(unavailable: {e})")
            return False
        self.out("")
        return True

    def _teach(self, question: Question, aid: Aid) -> None:
        """Training wheels: show the answer and how to get it, before asking."""
        if aid.truth is not None:
            self.out(f"  learn: the answer is {format_truth(question, aid.truth)}")
            if aid.explanation:
                self.out(f"  learn: {aid.explanation}")
        else:
            self.out("  learn: this is a forecast; its outcome isn't known until it happens.")
        if aid.lesson:
            for line in aid.lesson.splitlines():
                self.out(f"  learn: {line}")
        if question.tip:
            self.out(f"  learn: tip: {question.tip}")

    def _confirm(self, question: Question, aid: Aid, answer: Any) -> bool:
        """Show what the answer would score; True to keep it."""
        score, note = aid.judge(answer)
        if note:
            for line in note.splitlines():
                self.out(f"  check: {line}")
        wrong = score is not None and score.correct is False
        if wrong:
            self.out(
                f"  check: {format_answer(question, answer)} would be wrong "
                f"(error {score.error:.4f}). Press Enter to keep it, or type another answer."
            )
            return False
        if note:  # there is something to compare: let the player try other answers
            self.out("  check: press Enter to keep it, or type another answer to compare.")
            return False
        return True

    def ask(self, question: Question, aid: Aid | None = None) -> tuple[Any, float, bool]:
        hint = HINTS.get(question.kind)
        if question.kind is Kind.DECISION:
            keys = {v: k for k, v in question.params.get("keys", {}).items()}
            hint = " / ".join(f"{c} ({keys[c]})" if c in keys else c for c in question.choices)
            if len(question.choices) > 6:
                hint = f"a number from 1 to {len(question.choices)}, or the moves"
        if "hint" in question.params:
            hint = question.params["hint"]
        if question.params.get("unit") == "percent":
            hint = "a number, in %"
        if question.kind is Kind.INTERVAL and "max_width" in question.params:
            hint = f"bid ask, e.g. 9.5 11.5, at most {float(question.params['max_width']):g} apart"
        if question.params.get("unit") == "dollars" and "pct_base" in question.params:
            hint = "dollars: 5 on heads, -5 on tails, or 20% of your bankroll"
        extras = "s to skip, q to quit" if question.skippable else "q to quit"
        if self.tutor is not None:
            extras = "? to ask the tutor, " + extras
        self.out("")
        self.out(f"[{question.kind.value}] {question.prompt}")
        if hint:
            self.out(f"  ({hint}; {extras})")
        if aid is not None:
            self._teach(question, aid)
        start = self.clock()
        pending = None  # training wheels: an answer waiting to be confirmed
        assisted = False  # the tutor helped before a scored answer
        while True:
            try:
                text = self.input("> ")
            except EOFError:
                raise Quit() from None
            if text.strip().lower() in QUIT_WORDS:
                raise Quit()
            if text.strip().startswith("?"):
                helped = self._help(question, aid, text.strip()[1:].strip())
                assisted = assisted or (helped and aid is None)
                continue
            if pending is not None and not text.strip():
                return pending, self.clock() - start, assisted
            try:
                answer = parse_answer(question, text)
            except ParseError as e:
                self.out(f"  {e}")
                continue
            if aid is not None and not self._confirm(question, aid, answer):
                pending = answer
                continue
            return answer, self.clock() - start, assisted

    def reveal(self, turn: Turn) -> None:
        q, s = turn.question, turn.score
        if turn.answer is None:
            mark = "skipped"
        else:
            mark = {True: "correct", False: "wrong", None: "scored"}[s.correct]
        self.out(f"  you: {format_answer(q, turn.answer)} | truth: {format_truth(q, turn.truth)}")
        self.out(f"  {mark} | error {s.error:.4f} | points {s.points:.2f} | {turn.seconds:.1f}s")
        self.out(f"  {turn.explanation}")
        if q.tip and show_tip(turn):
            self.out(f"  tip: {q.tip}")
        if turn.assisted:
            self.out("  (assisted: the tutor helped before this answer)")
        if self.tutor is not None:
            self.tutor.note_reveal(
                f"{q.prompt} | player answered {format_answer(q, turn.answer)} | answer "
                f"{format_truth(q, turn.truth)} | {turn.explanation}"
            )
