from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app import database as db_module


def test_should_require_ssl() -> None:
    assert db_module._should_require_ssl("postgresql://test.supabase.net/db") is True
    assert db_module._should_require_ssl("postgresql://localhost/db") is False


def test_build_engine_kwargs_non_supabase(monkeypatch) -> None:
    monkeypatch.setattr(db_module, "DATABASE_POOL_CONFIG", None)
    kwargs = db_module._build_engine_kwargs("postgresql://localhost/db")
    connect_args = kwargs["connect_args"]

    assert "sslmode" not in connect_args
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20


def test_build_engine_kwargs_supabase(monkeypatch) -> None:
    monkeypatch.setattr(db_module, "DATABASE_POOL_CONFIG", None)
    kwargs = db_module._build_engine_kwargs("postgresql://db.supabase.net/db")

    assert kwargs["connect_args"].get("sslmode") == "require"


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
        overflow=lambda: 0,
    )
    monkeypatch.setattr(db_module, "engine", SimpleNamespace(pool=dummy_pool))

    status = db_module.get_db_pool_status()
    assert status == {"size": 3, "checked_in": 1, "checked_out": 2, "total": 3, "overflow": 0}


def test_event_handlers_update_and_log(monkeypatch) -> None:
    connection_record = SimpleNamespace(info={})

    db_module.receive_connect(None, connection_record)
    assert "connect_time" in connection_record.info

    db_module.receive_checkout(None, connection_record, None)
    db_module.receive_checkin(None, connection_record)
    db_module.receive_soft_invalidate(None, connection_record, None)

    dummy_pool = SimpleNamespace(size=lambda: 1, checkedout=lambda: 0)
    monkeypatch.setattr(db_module, "engine", SimpleNamespace(pool=dummy_pool))
    db_module.receive_invalidate(None, connection_record, Exception("boom"))


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
    monkeypatch.setattr(db_module, "SessionLocal", lambda: dummy)

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
    monkeypatch.setattr(db_module, "SessionLocal", lambda: dummy)

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
    monkeypatch.setattr(db_module, "SessionLocal", lambda: dummy)

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


def test_build_engine_kwargs_with_production_config(monkeypatch) -> None:
    monkeypatch.setattr(
        db_module,
        "DATABASE_POOL_CONFIG",
        {
            "pool_size": 9,
            "connect_args": {"application_name": "override"},
        },
    )

    kwargs = db_module._build_engine_kwargs("postgresql://db.supabase.net/db")
    assert kwargs["pool_size"] == 9
    assert kwargs["connect_args"]["application_name"] == "override"


def test_should_require_ssl_handles_parse_error(monkeypatch) -> None:
    import urllib.parse

    def _boom(_url):
        raise ValueError("bad")

    monkeypatch.setattr(urllib.parse, "urlparse", _boom)
    assert db_module._should_require_ssl("postgresql://bad") is False
