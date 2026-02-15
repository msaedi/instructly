from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app import database as db_module
from app.database import engines as engines_module, sessions as sessions_module


def test_should_require_ssl() -> None:
    assert engines_module._should_require_ssl("postgresql://test.supabase.net/db") is True
    assert engines_module._should_require_ssl("postgresql://localhost/db") is False


def test_build_connect_args_non_supabase() -> None:
    args = engines_module._build_connect_args(
        db_url="postgresql://localhost/db", statement_timeout_ms=15000, connect_timeout=5
    )
    assert "sslmode" not in args


def test_build_connect_args_supabase() -> None:
    args = engines_module._build_connect_args(
        db_url="postgresql://db.supabase.net/db", statement_timeout_ms=15000, connect_timeout=5
    )
    assert args.get("sslmode") == "require"


def test_retryable_db_error_detection() -> None:
    retryable = OperationalError("stmt", {}, Exception("server closed the connection"))
    non_retryable = OperationalError("stmt", {}, Exception("other error"))

    assert db_module._is_retryable_db_error(retryable) is True
    assert db_module._is_retryable_db_error(non_retryable) is False


def test_retry_delay(monkeypatch) -> None:
    monkeypatch.setattr(db_module.secrets, "randbelow", lambda *_args, **_kwargs: 0)
    assert db_module._retry_delay(1) == 0.1
    assert db_module._retry_delay(2) == 0.2


def test_with_db_retry_success_after_retry(monkeypatch) -> None:
    monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

    calls = {"count": 0}

    def _op() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OperationalError("stmt", {}, Exception("server closed the connection"))
        return "ok"

    result = db_module.with_db_retry("op", _op, max_attempts=2)
    assert result == "ok"
    assert calls["count"] == 2


def test_with_db_retry_non_retryable(monkeypatch) -> None:
    monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

    def _op() -> str:
        raise OperationalError("stmt", {}, Exception("bad"))

    with pytest.raises(OperationalError):
        db_module.with_db_retry("op", _op, max_attempts=2)


def test_with_db_retry_calls_on_retry_before_retry(monkeypatch) -> None:
    """on_retry callback is invoked before each retry attempt."""
    monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

    calls: list[str] = []

    def _op() -> str:
        calls.append("op")
        if len([c for c in calls if c == "op"]) == 1:
            raise OperationalError("stmt", {}, Exception("server closed the connection"))
        return "ok"

    def _on_retry() -> None:
        calls.append("rollback")

    result = db_module.with_db_retry("op", _op, max_attempts=2, on_retry=_on_retry)
    assert result == "ok"
    assert calls == ["op", "rollback", "op"]


def test_with_db_retry_on_retry_failure_does_not_prevent_retry(monkeypatch) -> None:
    """If on_retry raises, the retry still proceeds."""
    monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

    calls = {"count": 0}

    def _op() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OperationalError("stmt", {}, Exception("server closed the connection"))
        return "ok"

    def _bad_on_retry() -> None:
        raise RuntimeError("rollback failed")

    result = db_module.with_db_retry("op", _op, max_attempts=2, on_retry=_bad_on_retry)
    assert result == "ok"
    assert calls["count"] == 2


def test_with_db_retry_no_on_retry_when_no_retry(monkeypatch) -> None:
    """on_retry is NOT called on success."""
    called = False

    def _op() -> str:
        return "ok"

    def _on_retry() -> None:
        nonlocal called
        called = True

    result = db_module.with_db_retry("op", _op, on_retry=_on_retry)
    assert result == "ok"
    assert called is False


@pytest.mark.asyncio
async def test_with_db_retry_async_calls_on_retry(monkeypatch) -> None:
    """Async variant also invokes on_retry before retry."""
    monkeypatch.setattr(db_module.asyncio, "sleep", AsyncMock())

    calls: list[str] = []

    async def _op() -> str:
        calls.append("op")
        if len([c for c in calls if c == "op"]) == 1:
            raise OperationalError("stmt", {}, Exception("server closed the connection"))
        return "ok"

    def _on_retry() -> None:
        calls.append("rollback")

    result = await db_module.with_db_retry_async("op", _op, max_attempts=2, on_retry=_on_retry)
    assert result == "ok"
    assert calls == ["op", "rollback", "op"]


@pytest.mark.asyncio
async def test_with_db_retry_async_success(monkeypatch) -> None:
    monkeypatch.setattr(db_module.asyncio, "sleep", AsyncMock())

    calls = {"count": 0}

    async def _op() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OperationalError("stmt", {}, Exception("server closed the connection"))
        return "ok"

    result = await db_module.with_db_retry_async("op", _op, max_attempts=2)
    assert result == "ok"


def test_get_db_pool_status(monkeypatch) -> None:
    dummy_pool = SimpleNamespace(
        size=lambda: 3,
        checkedin=lambda: 1,
        checkedout=lambda: 2,
        overflow=lambda: -1,
        _max_overflow=2,
    )
    monkeypatch.setattr(
        db_module, "get_engine_for_role", lambda _role=None: SimpleNamespace(pool=dummy_pool)
    )

    status = db_module.get_db_pool_status()
    assert status["size"] == 3
    assert status["max_overflow"] == 2
    assert status["max_capacity"] == 5
    assert status["checked_in"] == 1
    assert status["checked_out"] == 2
    assert status["overflow_in_use"] == -1
    assert status["utilization_pct"] == 40.0


def test_get_db_pool_statuses(monkeypatch) -> None:
    api_pool = SimpleNamespace(
        size=lambda: 1,
        checkedin=lambda: 0,
        checkedout=lambda: 1,
        overflow=lambda: 0,
        _max_overflow=1,
    )
    worker_pool = SimpleNamespace(
        size=lambda: 2,
        checkedin=lambda: 2,
        checkedout=lambda: 0,
        overflow=lambda: -2,
        _max_overflow=1,
    )
    scheduler_pool = SimpleNamespace(
        size=lambda: 3,
        checkedin=lambda: 1,
        checkedout=lambda: 2,
        overflow=lambda: -1,
        _max_overflow=2,
    )

    monkeypatch.setattr(db_module, "get_api_engine", lambda: SimpleNamespace(pool=api_pool))
    monkeypatch.setattr(db_module, "get_worker_engine", lambda: SimpleNamespace(pool=worker_pool))
    monkeypatch.setattr(
        db_module, "get_scheduler_engine", lambda: SimpleNamespace(pool=scheduler_pool)
    )

    statuses = db_module.get_db_pool_statuses()
    assert statuses["api"]["size"] == 1
    assert statuses["worker"]["max_capacity"] == 3
    assert statuses["scheduler"]["checked_out"] == 2


def test_pool_status_from_engine_uses_max_overflow() -> None:
    dummy_pool = SimpleNamespace(
        size=lambda: 2,
        checkedin=lambda: 1,
        checkedout=lambda: 1,
        overflow=lambda: -1,
        _max_overflow=2,
    )
    status = db_module._pool_status_from_engine(SimpleNamespace(pool=dummy_pool))
    assert status["max_capacity"] == 4
    assert status["utilization_pct"] == 25.0
    assert status["overflow_in_use"] == -1


def test_get_pool_status_for_role(monkeypatch) -> None:
    import app.core.config as config_module

    api_pool = SimpleNamespace(
        size=lambda: 1,
        checkedin=lambda: 0,
        checkedout=lambda: 1,
        overflow=lambda: 0,
        _max_overflow=1,
    )
    worker_pool = SimpleNamespace(
        size=lambda: 2,
        checkedin=lambda: 2,
        checkedout=lambda: 0,
        overflow=lambda: -2,
        _max_overflow=1,
    )
    scheduler_pool = SimpleNamespace(
        size=lambda: 3,
        checkedin=lambda: 1,
        checkedout=lambda: 2,
        overflow=lambda: -1,
        _max_overflow=2,
    )

    monkeypatch.setattr(db_module, "get_api_engine", lambda: SimpleNamespace(pool=api_pool))
    monkeypatch.setattr(db_module, "get_worker_engine", lambda: SimpleNamespace(pool=worker_pool))
    monkeypatch.setattr(
        db_module, "get_scheduler_engine", lambda: SimpleNamespace(pool=scheduler_pool)
    )
    monkeypatch.setattr(
        config_module, "settings", SimpleNamespace(service_role="api"), raising=False
    )

    api_only = db_module.get_pool_status_for_role()
    assert list(api_only.keys()) == ["api"]

    all_pools = db_module.get_pool_status_for_role("all")
    assert set(all_pools.keys()) == {"api", "worker", "scheduler"}


def test_get_db_with_retry_cleanup_errors(monkeypatch) -> None:
    class DummySession:
        def connection(self):
            raise OperationalError("stmt", {}, Exception("server closed the connection"))

        def rollback(self):
            raise RuntimeError("rollback")

        def close(self):
            raise RuntimeError("close")

    monkeypatch.setattr(db_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

    gen = db_module.get_db_with_retry(max_attempts=1)
    with pytest.raises(OperationalError):
        next(gen)


def test_get_db_commits_and_closes(monkeypatch) -> None:
    class DummySession:
        def __init__(self):
            self.committed = False
            self.closed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("rollback should not be called")

        def close(self):
            self.closed = True

    dummy = DummySession()
    monkeypatch.setattr(sessions_module, "SessionLocal", lambda: dummy)

    gen = db_module.get_db()
    assert next(gen) is dummy
    with pytest.raises(StopIteration):
        next(gen)

    assert dummy.committed is True
    assert dummy.closed is True


def test_get_db_rolls_back_on_exception(monkeypatch) -> None:
    class DummySession:
        def __init__(self):
            self.rolled_back = False
            self.closed = False

        def commit(self):
            raise AssertionError("commit should not be called")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    dummy = DummySession()
    monkeypatch.setattr(sessions_module, "SessionLocal", lambda: dummy)

    gen = db_module.get_db()
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))

    assert dummy.rolled_back is True
    assert dummy.closed is True


def test_get_db_session_context_manager(monkeypatch) -> None:
    class DummySession:
        def __init__(self):
            self.rolled_back = False
            self.closed = False
            self.committed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    dummy = DummySession()
    monkeypatch.setattr(sessions_module, "SessionLocal", lambda: dummy)

    with pytest.raises(RuntimeError):
        with db_module.get_db_session() as session:
            assert session is dummy
            raise RuntimeError("boom")

    assert dummy.rolled_back is True
    assert dummy.closed is True


def test_get_db_with_retry_handles_transient(monkeypatch) -> None:
    monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

    class DummySession:
        def __init__(self, should_fail: bool):
            self.should_fail = should_fail
            self.closed = False
            self.committed = False
            self.rolled_back = False

        def connection(self):
            if self.should_fail:
                raise OperationalError("stmt", {}, Exception("server closed the connection"))
            return None

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    sessions = [DummySession(True), DummySession(False)]

    def _factory():
        return sessions.pop(0)

    monkeypatch.setattr(db_module, "SessionLocal", _factory)

    gen = db_module.get_db_with_retry(max_attempts=2)
    session = next(gen)
    assert session is not None
    with pytest.raises(StopIteration):
        next(gen)

    assert session.committed is True


def test_build_connect_args_respects_timeouts() -> None:
    args = engines_module._build_connect_args(
        db_url="postgresql://db.supabase.net/db",
        statement_timeout_ms=12345,
        connect_timeout=7,
    )
    assert args["options"] == "-c statement_timeout=12345"
    assert args["connect_timeout"] == 7


def test_should_require_ssl_handles_parse_error(monkeypatch) -> None:
    def _boom(_url):
        raise ValueError("bad")

    monkeypatch.setattr(engines_module, "urlparse", _boom)
    assert engines_module._should_require_ssl("postgresql://bad") is False
