import json

from edge_engine.core import Kind, Question
from edge_engine.scoring import Score
from edge_engine.storage import Store

Q1 = Question(id="a", kind=Kind.POINT, prompt="p?", category="slow", tolerance=0.1)
Q2 = Question(id="b", kind=Kind.PROBABILITY, prompt="f?", category="fast")


def test_log_and_stats(tmp_path):
    db = tmp_path / "sub" / "h.db"
    with Store(db) as store:
        sid = store.start_session("dice", 7, {"rounds": 2})
        store.log_answer(sid, Q1, 0.5, 0.45, Score(0.05, 1.0, True), 9.0)
        store.log_answer(sid, Q1, 0.9, 0.45, Score(0.45, 0.0, False), 7.0)
        store.log_answer(sid, Q2, 0.7, 1, Score(0.09, 0.91, None), 2.0)
        store.end_session(sid)
        assert store.answer_count(sid) == 3

    with Store(db) as store:  # data persists across connections
        rows = store.category_stats()
        assert [r.category for r in rows] == ["slow", "fast"]  # slowest first
        slow, fast = rows
        assert slow.n == 2 and slow.accuracy == 0.5 and slow.mean_seconds == 8.0
        assert fast.accuracy is None and fast.mean_points == 0.91
        assert store.category_stats("other") == []
        cfg, ended = store.conn.execute("SELECT config, ended_at FROM sessions").fetchone()
        assert json.loads(cfg) == {"rounds": 2} and ended is not None


def test_memory_store_stores_json():
    store = Store(":memory:")
    sid = store.start_session("dice", 1, {})
    store.log_answer(sid, Q1, (1, 2), {"take": 0.1}, Score(0, 1, True), 1.0)
    answer, truth = store.conn.execute("SELECT answer, truth FROM answers").fetchone()
    assert json.loads(answer) == [1, 2] and json.loads(truth) == {"take": 0.1}
