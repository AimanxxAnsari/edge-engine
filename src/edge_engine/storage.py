"""SQLite log of sessions and answers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import Question
from .scoring import Score

DEFAULT_DB = Path.home() / ".edge_engine" / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    module      TEXT NOT NULL,
    seed        INTEGER NOT NULL,
    config      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES sessions(id),
    question_id TEXT NOT NULL,
    kind        TEXT NOT NULL,
    category    TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    answer      TEXT NOT NULL,
    truth       TEXT NOT NULL,
    error       REAL NOT NULL,
    points      REAL NOT NULL,
    correct     INTEGER,
    seconds     REAL NOT NULL,
    created_at  TEXT NOT NULL,
    assisted    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS answers_session ON answers(session_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class CategoryStats:
    module: str
    category: str
    n: int
    accuracy: float | None  # share correct, over answers where "correct" is defined
    mean_points: float
    mean_error: float
    mean_seconds: float


class Store:
    """Thin wrapper over one SQLite file. Use ':memory:' for tests."""

    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(answers)")}
        if "assisted" not in columns:  # history files from before the tutor
            self.conn.execute("ALTER TABLE answers ADD COLUMN assisted INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def start_session(self, module: str, seed: int, config: Mapping[str, Any]) -> int:
        cur = self.conn.execute(
            "INSERT INTO sessions (module, seed, config, started_at) VALUES (?, ?, ?, ?)",
            (module, seed, json.dumps(dict(config), sort_keys=True), _now()),
        )
        self.conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def end_session(self, session_id: int) -> None:
        self.conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (_now(), session_id))
        self.conn.commit()

    def log_answer(
        self,
        session_id: int,
        question: Question,
        answer: Any,
        truth: Any,
        score: Score,
        seconds: float,
        assisted: bool = False,
    ) -> None:
        correct = None if score.correct is None else int(score.correct)
        self.conn.execute(
            """INSERT INTO answers (session_id, question_id, kind, category, prompt, answer,
                   truth, error, points, correct, seconds, created_at, assisted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                question.id,
                question.kind.value,
                question.category,
                question.prompt,
                json.dumps(answer, default=str),
                json.dumps(truth, default=str),
                score.error,
                score.points,
                correct,
                seconds,
                _now(),
                int(assisted),
            ),
        )
        self.conn.commit()

    def answer_count(self, session_id: int | None = None) -> int:
        if session_id is None:
            row = self.conn.execute("SELECT COUNT(*) FROM answers").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM answers WHERE session_id = ?", (session_id,)
            ).fetchone()
        return int(row[0])

    def category_stats(self, module: str | None = None) -> list[CategoryStats]:
        """Per-category totals, slowest average time first."""
        sql = """
            SELECT s.module, a.category, COUNT(*), AVG(a.correct), AVG(a.points),
                   AVG(a.error), AVG(a.seconds)
            FROM answers a JOIN sessions s ON s.id = a.session_id
            {where}
            GROUP BY s.module, a.category
            ORDER BY AVG(a.seconds) DESC
        """
        if module is None:
            rows = self.conn.execute(sql.format(where="")).fetchall()
        else:
            rows = self.conn.execute(sql.format(where="WHERE s.module = ?"), (module,)).fetchall()
        return [CategoryStats(*row) for row in rows]
