import argparse

import pytest

from edge_engine.cli import main
from edge_engine.core import Kind, Question
from edge_engine.loop import Quit
from edge_engine.terminal import ParseError, TerminalUI, parse_answer, parse_number

POINT = Question(id="p", kind=Kind.POINT, prompt="?", category="c", tolerance=0.1)
PROB = Question(id="f", kind=Kind.PROBABILITY, prompt="?", category="c")
DEC = Question(id="d", kind=Kind.DECISION, prompt="?", category="c", choices=("take", "pass"))
INT = Question(id="i", kind=Kind.INTERVAL, prompt="?", category="c")


@pytest.mark.parametrize(
    "text,value",
    [("0.25", 0.25), ("1/4", 0.25), ("25%", 0.25), (" -3 ", -3.0), ("1,000", 1000.0)],
)
def test_parse_number(text, value):
    assert parse_number(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["", "abc", "1/0", "1/x"])
def test_parse_number_errors(text):
    with pytest.raises(ParseError):
        parse_number(text)


def test_parse_by_kind():
    assert parse_answer(DEC, "T") == "take"
    assert parse_answer(DEC, "2") == "pass"
    assert parse_answer(INT, "3 7") == (3.0, 7.0)
    assert parse_answer(INT, "3 to 7") == (3.0, 7.0)
    assert parse_answer(PROB, "30%") == pytest.approx(0.3)
    for q, text in [(DEC, "x"), (DEC, ""), (INT, "7 3"), (INT, "1"), (PROB, "1.5")]:
        with pytest.raises(ParseError):
            parse_answer(q, text)


def test_ui_reprompts_and_times():
    inputs = iter(["nope", "0.5"])
    times = iter([10.0, 13.5])
    out = []
    ui = TerminalUI(lambda _: next(inputs), out.append, lambda: next(times))
    answer, seconds = ui.ask(POINT)
    assert answer == 0.5 and seconds == 3.5
    assert any("not a number" in line for line in out)


@pytest.mark.parametrize("text", ["q", "QUIT", "exit"])
def test_ui_quit(text):
    ui = TerminalUI(lambda _: text, lambda s: None)
    with pytest.raises(Quit):
        ui.ask(POINT)


def test_ui_eof_quits():
    def eof(_):
        raise EOFError

    with pytest.raises(Quit):
        TerminalUI(eof, lambda s: None).ask(POINT)


def test_cli_play_and_stats(tmp_path, monkeypatch, capsys):
    db = tmp_path / "h.db"
    answers = iter(["10", "0.3", "pass", "0.3"] * 2)
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["play", "dice", "--seed", "5", "--rounds", "2", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "seed 5" in out and "Session finished: 8 answers" in out
    assert main(["stats", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    for category in ["dice-counting", "dice-probability", "ev-decision", "forecast"]:
        assert category in out


def test_cli_list_and_empty_stats(tmp_path, capsys):
    assert main(["list"]) == 0
    assert "dice" in capsys.readouterr().out
    assert main(["stats", "--db", str(tmp_path / "none.db")]) == 0
    assert "No history" in capsys.readouterr().out


def test_parse_option():
    from edge_engine.cli import parse_option

    assert parse_option("mode=test") == ("mode", "test")
    assert parse_option("seconds=60") == ("seconds", 60)
    assert parse_option("seconds=1.5") == ("seconds", 1.5)
    assert parse_option("adaptive=False") == ("adaptive", False)
    assert parse_option("categories=odds,percent") == ("categories", "odds,percent")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_option("novalue")


def test_cli_mental_options_and_errors(tmp_path, monkeypatch, capsys):
    db = tmp_path / "h.db"
    answers = iter(["s", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    args = ["play", "mental", "--seed", "1", "--db", str(db), "-o", "mode=test"]
    assert main(args + ["-o", "categories=odds"]) == 0
    out = capsys.readouterr().out
    assert "[test]" in out and "skipped" in out and "tip:" in out
    assert main(args + ["-o", "mode=race"]) == 2
    assert "error: unknown mode" in capsys.readouterr().out
