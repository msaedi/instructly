"""Coverage tests for admin audit routes — L72-73: prometheus_metrics.record_audit_read failure."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.v1.admin import audit as routes


class _FakeRepo:
    def list(self, **_kwargs):
        item = SimpleNamespace(
            id="audit-1",
            entity_type="user",
            entity_id="u-1",
            action="update",
            actor_id="admin-1",
            actor_role="admin",
            occurred_at=datetime.now(timezone.utc),
            before={"name": "Old"},
            after={"name": "New"},
        )
        return [item], 1


# ---- L72-73: prometheus_metrics.record_audit_read raises, caught silently ----
@pytest.mark.asyncio
async def test_list_audit_logs_prometheus_failure(monkeypatch):
    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_audit_repository",
        lambda _db: _FakeRepo(),
    )

    class _FailingMetrics:
        def record_audit_read(self, _duration):
            raise RuntimeError("prometheus down")

    monkeypatch.setattr(routes, "prometheus_metrics", _FailingMetrics())

    result = await routes.list_audit_logs(db=None)
    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].action == "update"


# ---- Normal success path ----
@pytest.mark.asyncio
async def test_list_audit_logs_success(monkeypatch):
    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_audit_repository",
        lambda _db: _FakeRepo(),
    )

    class _Metrics:
        def __init__(self):
            self.calls = []

        def record_audit_read(self, duration):
            self.calls.append(duration)

    metrics = _Metrics()
    monkeypatch.setattr(routes, "prometheus_metrics", metrics)

    result = await routes.list_audit_logs(db=None, limit=50, offset=0)
    assert result.total == 1
    assert len(metrics.calls) == 1
