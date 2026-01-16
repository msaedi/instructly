from __future__ import annotations

from types import SimpleNamespace

from app.repositories.metrics_repository import MetricsRepository


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


def test_get_active_connections_count(db, monkeypatch):
    repo = MetricsRepository(db)

    monkeypatch.setattr(repo.db, "execute", lambda *_args, **_kwargs: _ScalarResult(3))
    assert repo.get_active_connections_count() == 3


def test_get_slow_queries_success_and_failure(db, monkeypatch):
    repo = MetricsRepository(db)

    rows = [
        SimpleNamespace(query="select 1", mean_exec_time=150.0, calls=2, total_exec_time=300.0),
        SimpleNamespace(query="select 2", mean_exec_time=120.0, calls=1, total_exec_time=120.0),
    ]

    monkeypatch.setattr(repo.db, "execute", lambda *_args, **_kwargs: rows)
    results = repo.get_slow_queries(min_mean_exec_time_ms=100, limit=2)
    assert results[0]["query"] == "select 1"
    assert results[1]["calls"] == 1

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "execute", _raise)
    assert repo.get_slow_queries() == []
