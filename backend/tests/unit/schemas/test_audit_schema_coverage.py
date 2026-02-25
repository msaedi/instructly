"""Tests for app/schemas/audit.py — coverage gaps L45-46."""
from __future__ import annotations

import pytest

from app.schemas.audit import AuditLogListResponse, AuditLogView


@pytest.mark.unit
class TestAuditSchemaCoverage:
    """Cover the except block in model_rebuild (L45-46)."""

    def test_model_rebuild_exception_is_silent(self) -> None:
        """L45-46: model_rebuild() failure is caught and logged silently."""
        import importlib

        from pydantic import BaseModel

        import app.schemas.audit as audit_module

        # Patch BaseModel.model_rebuild to raise so that when the module reloads
        # and calls AuditLogView.model_rebuild(), it hits the except branch.
        original_rebuild = BaseModel.model_rebuild
        try:
            BaseModel.model_rebuild = classmethod(  # type: ignore[assignment]
                lambda cls, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
            )
            importlib.reload(audit_module)
        finally:
            BaseModel.model_rebuild = original_rebuild  # type: ignore[assignment]
            # Reload again to restore normal state
            importlib.reload(audit_module)

        # Module loaded without error — the except branch swallowed it
        assert hasattr(audit_module, "AuditLogView")
        assert hasattr(audit_module, "AuditLogListResponse")

    def test_audit_log_view_basic(self) -> None:
        """Smoke test for AuditLogView."""
        from datetime import datetime, timezone

        view = AuditLogView(
            id="01ABC",
            entity_type="user",
            entity_id="01DEF",
            action="update",
            occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert view.action == "update"
        assert view.actor_id is None

    def test_audit_log_list_response(self) -> None:
        from datetime import datetime, timezone

        view = AuditLogView(
            id="01ABC",
            entity_type="user",
            entity_id="01DEF",
            action="create",
            occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        resp = AuditLogListResponse(items=[view], total=1, limit=10, offset=0)
        assert resp.total == 1
        assert len(resp.items) == 1
