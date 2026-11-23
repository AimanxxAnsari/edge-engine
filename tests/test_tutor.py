import sqlite3
from types import SimpleNamespace

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind, Question
from edge_engine.loop import run_session
from edge_engine.modules.dice import DiceDemo
from edge_engine.storage import Store
from edge_engine.terminal import TerminalUI
from edge_engine.tutor import PRICES, Context, Tutor, TutorError, Usage


class FakeStream:
    def __init__(self, chunks, usage, stop_reason):
        self.text_stream = iter(chunks)
        self._final = SimpleNamespace(usage=usage, stop_reason=stop_reason)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


class FakeClient:
    """Records every request; answers with fixed text and usage."""

    def __init__(self, reply="Think about the 36 outcomes.", stop_reason="end_turn", error=None):
        self.calls = []
        self.reply, self.stop_reason, self.error = reply, stop_reason, error
        usage = SimpleNamespace(
            input_tokens=200,
            output_tokens=50,
            cache_read_input_tokens=3000,
            cache_creation_input_tokens=0,
        )
        outer = self

        class Messages:
            def stream(self, **kwargs):
                outer.calls.append(kwargs)
                if outer.error:
                    raise outer.error
                half = len(outer.reply) // 2  # stream in two pieces, like real chunks
                chunks = [outer.reply[:half], outer.reply[half:]]
                return FakeStream(chunks, usage, outer.stop_reason)

        self.beta = SimpleNamespace(messages=Messages())


def user_text(call):
    return call["messages"][-1]["content"]


def scripted_ui(inputs, tutor):
    it = iter(inputs)
    lines, written = [], []
    ui = TerminalUI(
        lambda _: next(it), lines.append, clock=lambda: 0.0, tutor=tutor, write=written.append
    )
    return ui, lines, written


# --- what Claude is (and is not) sent -------------------------------------------------


def test_scored_mode_hides_the_answer_and_marks_assisted():
    client = FakeClient()
    tutor = Tutor("dice", client=client)
    inputs = iter(["? how do I count these", "21", "0.58", "take", "0.6"])
    ui = TerminalUI(
        lambda _: next(inputs), lambda s: None, clock=lambda: 0.0, tutor=tutor, write=lambda s: None
    )
    store = Store(":memory:")
    res = run_session(
        DiceDemo(),
        seed=4,
        ask=ui.ask,
        config={"rounds": 1},
        reveal=ui.reveal,
        show=ui.show,
        store=store,
    )
    first = res.turns[0]
    assert first.assisted and res.assisted == 1
    sent = user_text(client.calls[0])
    assert "Answer: HIDDEN" in sent and "how do I count these" in sent
    assert str(int(first.truth)) not in sent.split("Question:")[1].split("PLAYER")[0]
    flags = [r[0] for r in store.conn.execute("SELECT assisted FROM answers ORDER BY id")]
    assert flags == [1, 0, 0, 0]


def test_training_wheels_sends_the_exact_answer_and_is_not_assisted():
    client = FakeClient()
    tutor = Tutor("dice", client=client)
    inputs = iter(["? why", "21", "0.58", "take", "0.6"])
    ui = TerminalUI(
        lambda _: next(inputs), lambda s: None, clock=lambda: 0.0, tutor=tutor, write=lambda s: None
    )
    res = run_session(
        DiceDemo(),
        seed=4,
        ask=ui.ask,
        config={"rounds": 1},
        reveal=ui.reveal,
        show=ui.show,
        wheels=True,
    )
    sent = user_text(client.calls[0])
    truth = int(res.turns[0].truth)
    assert f"Answer (exact, from the game's engine): {truth}" in sent
    assert "Explanation:" in sent and res.assisted == 0


def test_request_settings_and_system_prompt():
    client = FakeClient()
    tutor = Tutor("blackjack", client=client)
    tutor.ask(Context(screen="Dealer: 10 ?", question="Hit?"), "help", lambda s: None)
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "low"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    system = call["system"][0]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "Never invent probabilities" in system["text"]
    assert "Basic strategy" in system["text"]  # the public docs explainer
    assert "local-brain" not in system["text"].replace("local-brain/ is", "")


def test_history_and_reveals_carry_over():
    client = FakeClient(reply="Because the dealer busts often.")
    tutor = Tutor("dice", client=client)
    tutor.ask(Context(screen="", question="Q1", answer="5"), "why", lambda s: None)
    tutor.note_reveal("Q1 | player answered 4 | answer 5 | explanation")
    tutor.ask(Context(screen="", question="Q2"), "why was I wrong?", lambda s: None)
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"] == "Because the dealer busts often."
    assert "player answered 4" in second[2]["content"]


def test_cost_and_summary():
    u = Usage()
    u.add(
        SimpleNamespace(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
            cache_creation_input_tokens=0,
        )
    )
    p_in, p_out, p_read, _ = PRICES["claude-opus-5-5"]
    assert u.cost("claude-opus-5-5") == pytest.approx(p_in + p_out + p_read)
    assert u.cost("some-other-model") is None
    tutor = Tutor("dice", client=FakeClient())
    assert tutor.summary() == ""
    tutor.ask(Context(screen="", question="Q"), "hi", lambda s: None)
    assert "1 question(s)" in tutor.summary() and "$" in tutor.summary()


# --- failures never break the game ------------------------------------------------------


def test_errors_and_refusals():
    class AuthenticationError(Exception):
        pass

    tutor = Tutor("dice", client=FakeClient(error=AuthenticationError("bad key")))
    with pytest.raises(TutorError, match="credentials"):
        tutor.ask(Context(screen="", question="Q"), "hi", lambda s: None)
    refusing = Tutor("dice", client=FakeClient(stop_reason="refusal"))
    with pytest.raises(TutorError, match="declined"):
        refusing.ask(Context(screen="", question="Q"), "hi", lambda s: None)


def test_ui_survives_tutor_errors_and_does_not_mark_assisted():
    class APIConnectionError(Exception):
        pass

    q = Question(id="x", kind=Kind.POINT, prompt="?", category="c")
    tutor = Tutor("dice", client=FakeClient(error=APIConnectionError()))
    ui, lines, _ = scripted_ui(["?", "3"], tutor)
    answer, _, assisted = ui.ask(q)
    assert answer == 3 and not assisted
    assert any("unavailable: cannot reach the API" in line for line in lines)


def test_tutor_off():
    q = Question(id="x", kind=Kind.POINT, prompt="?", category="c")
    ui, lines, _ = scripted_ui(["? help", "3"], None)
    assert ui.ask(q)[2] is False
    assert any("tutor is off" in line for line in lines)


def test_old_history_files_gain_the_assisted_column(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """CREATE TABLE sessions (id INTEGER PRIMARY KEY, module TEXT NOT NULL,
               seed INTEGER NOT NULL, config TEXT NOT NULL, started_at TEXT NOT NULL,
               ended_at TEXT);
           CREATE TABLE answers (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,
               question_id TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL,
               prompt TEXT NOT NULL, answer TEXT NOT NULL, truth TEXT NOT NULL,
               error REAL NOT NULL, points REAL NOT NULL, correct INTEGER,
               seconds REAL NOT NULL, created_at TEXT NOT NULL);"""
    )
    conn.close()
    with Store(db) as store:
        cols = {r[1] for r in store.conn.execute("PRAGMA table_info(answers)")}
        assert "assisted" in cols


def test_cli_with_tutor(tmp_path, monkeypatch, capsys):
    client = FakeClient(reply="Count the sums from 7 up.")
    monkeypatch.setattr(
        "edge_engine.cli.Tutor", lambda game, model: Tutor(game, model=model, client=client)
    )
    answers = iter(["? hint please", "21", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    args = ["play", "dice", "--seed", "4", "--tutor", "--db", str(tmp_path / "h.db")]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Tutor on (claude-opus-5-5)" in out and "Count the sums" in out
    assert "1 answer(s) were assisted" in out and "Tutor (claude-opus-5-5): 1 question(s)" in out


def test_missing_key_gives_a_plain_message():
    err = TypeError('"Could not resolve authentication method. Expected one of api_key"')
    tutor = Tutor("dice", client=FakeClient(error=err))
    with pytest.raises(TutorError, match="no API key found: set ANTHROPIC_API_KEY"):
        tutor.ask(Context(screen="", question="Q"), "hi", lambda s: None)
