from __future__ import annotations

import pytest

from app.database import sessions as sessions_module


class _DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_default_role_parsing(monkeypatch) -> None:
    monkeypatch.delenv("DB_POOL_ROLE", raising=False)
    assert sessions_module._default_role() == "api"

    monkeypatch.setenv("DB_POOL_ROLE", "  WORKER ")
    assert sessions_module._default_role() == "worker"

    monkeypatch.setenv("DB_POOL_ROLE", "   ")
    assert sessions_module._default_role() == "api"


def test_select_default_sessionmaker_by_role(monkeypatch) -> None:
    monkeypatch.setattr(sessions_module, "_default_role", lambda: "worker")
    assert sessions_module._select_default_sessionmaker() is sessions_module.WorkerSessionLocal

    monkeypatch.setattr(sessions_module, "_default_role", lambda: "scheduler")
    assert sessions_module._select_default_sessionmaker() is sessions_module.SchedulerSessionLocal

    monkeypatch.setattr(sessions_module, "_default_role", lambda: "something-else")
    assert sessions_module._select_default_sessionmaker() is sessions_module.APISessionLocal


def test_init_session_factories_updates_sessionlocal(monkeypatch) -> None:
    original = sessions_module.SessionLocal
    selected = object()
    calls: list[str] = []

    monkeypatch.setattr(sessions_module, "_bind_session_factories", lambda: calls.append("bind"))
    monkeypatch.setattr(sessions_module, "_select_default_sessionmaker", lambda: selected)
    try:
        sessions_module.init_session_factories()
        assert calls == ["bind"]
        assert sessions_module.SessionLocal is selected
    finally:
        sessions_module.SessionLocal = original


@pytest.mark.parametrize(
    ("factory_attr", "ctx_getter"),
    [
        ("APISessionLocal", sessions_module.get_api_session),
        ("WorkerSessionLocal", sessions_module.get_worker_session),
        ("SchedulerSessionLocal", sessions_module.get_scheduler_session),
    ],
)
def test_role_scoped_context_managers_commit_and_close(monkeypatch, factory_attr, ctx_getter) -> None:
    dummy = _DummySession()
    monkeypatch.setattr(sessions_module, factory_attr, lambda: dummy)

    with ctx_getter() as session:
        assert session is dummy

    assert dummy.committed is True
    assert dummy.rolled_back is False
    assert dummy.closed is True


@pytest.mark.parametrize(
    ("factory_attr", "ctx_getter"),
    [
        ("APISessionLocal", sessions_module.get_api_session),
        ("WorkerSessionLocal", sessions_module.get_worker_session),
        ("SchedulerSessionLocal", sessions_module.get_scheduler_session),
    ],
)
def test_role_scoped_context_managers_rollback_on_error(monkeypatch, factory_attr, ctx_getter) -> None:
    dummy = _DummySession()
    monkeypatch.setattr(sessions_module, factory_attr, lambda: dummy)

    with pytest.raises(RuntimeError):
        with ctx_getter():
            raise RuntimeError("boom")

    assert dummy.committed is False
    assert dummy.rolled_back is True
    assert dummy.closed is True


def test_get_db_generator_commit_and_close(monkeypatch) -> None:
    dummy = _DummySession()
    monkeypatch.setattr(sessions_module, "SessionLocal", lambda: dummy)

    gen = sessions_module.get_db()
    yielded = next(gen)
    assert yielded is dummy
    with pytest.raises(StopIteration):
        next(gen)

    assert dummy.committed is True
    assert dummy.rolled_back is False
    assert dummy.closed is True


def test_get_db_generator_rolls_back_on_exception(monkeypatch) -> None:
    dummy = _DummySession()
    monkeypatch.setattr(sessions_module, "SessionLocal", lambda: dummy)

    gen = sessions_module.get_db()
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("db-failure"))

    assert dummy.committed is False
    assert dummy.rolled_back is True
    assert dummy.closed is True


def test_get_db_session_context_manager_commit_and_rollback(monkeypatch) -> None:
    ok = _DummySession()
    boom = _DummySession()
    sessions = [ok, boom]
    monkeypatch.setattr(sessions_module, "SessionLocal", lambda: sessions.pop(0))

    with sessions_module.get_db_session() as db:
        assert db is ok

    with pytest.raises(ValueError):
        with sessions_module.get_db_session():
            raise ValueError("boom")

    assert ok.committed is True and ok.closed is True and ok.rolled_back is False
    assert boom.committed is False and boom.closed is True and boom.rolled_back is True
