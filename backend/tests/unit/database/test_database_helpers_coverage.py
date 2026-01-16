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
    monkeypatch.setattr(db_module.random, "uniform", lambda *_args, **_kwargs: 0.0)
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
