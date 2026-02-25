"""Coverage tests for admin MCP instructors routes — L60-61: ValueError → 400."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import NotFoundException
from app.routes.v1.admin.mcp import instructors as routes


class _FailingService:
    def list_instructors(self, **_kwargs):
        raise ValueError("Invalid filter value")


class _NotFoundService:
    def get_instructor_detail(self, _identifier: str):
        raise NotFoundException("Instructor not found")


def _principal():
    return SimpleNamespace(id="p-1", identifier="admin@example.com", principal_type="service_token")


# ---- L60-61: ValueError in list_instructors → 400 ----
@pytest.mark.asyncio
async def test_list_instructors_value_error(monkeypatch):
    monkeypatch.setattr(routes, "MCPInstructorService", lambda _db: _FailingService())

    with pytest.raises(HTTPException) as exc:
        await routes.list_instructors(
            principal=_principal(),
            db=None,
        )
    assert exc.value.status_code == 400


# ---- NotFoundException in get_instructor_detail → 404 ----
@pytest.mark.asyncio
async def test_get_instructor_detail_not_found(monkeypatch):
    monkeypatch.setattr(routes, "MCPInstructorService", lambda _db: _NotFoundService())

    with pytest.raises(HTTPException) as exc:
        await routes.get_instructor_detail(
            identifier="missing-id",
            principal=_principal(),
            db=None,
        )
    assert exc.value.status_code == 404
