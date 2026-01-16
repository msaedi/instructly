from __future__ import annotations

from types import SimpleNamespace

from app.core.privacy_auditor import ViolationSeverity
import app.tasks.privacy_audit_task as tasks


def test_audit_privacy_production_success(monkeypatch):
    violation = SimpleNamespace(
        severity=ViolationSeverity.HIGH,
        method="GET",
        endpoint="/v1/test",
        message="bad",
    )
    result = SimpleNamespace(violations=[violation], execution_time=1.23)

    async def _run_privacy_audit(**_kwargs):
        return result, None

    monkeypatch.setattr(tasks, "run_privacy_audit", _run_privacy_audit)

    response = tasks.audit_privacy_production.run()

    assert response["status"] == "completed"
    assert response["violations"]["total"] == 1
    assert response["violations"]["high"] == 1


def test_audit_privacy_production_error(monkeypatch):
    async def _boom(**_kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(tasks, "run_privacy_audit", _boom)

    response = tasks.audit_privacy_production.run()

    assert response["status"] == "failed"
    assert "fail" in response["error"]
