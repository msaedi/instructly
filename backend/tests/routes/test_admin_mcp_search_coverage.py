"""Coverage tests for admin MCP search routes — L36: start_date_after_end_date."""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException
import pytest

from app.routes.v1.admin.mcp import search as routes


# ---- L36: _resolve_date_range start_date > end_date ----
def test_resolve_date_range_start_after_end():
    with pytest.raises(HTTPException) as exc:
        routes._resolve_date_range(date(2025, 6, 10), date(2025, 6, 1))
    assert exc.value.status_code == 400
    assert "start_date_after_end_date" in exc.value.detail


def test_resolve_date_range_defaults():
    start, end = routes._resolve_date_range(None, None)
    assert start is not None
    assert end is not None
    assert start <= end


def test_resolve_date_range_explicit():
    start, end = routes._resolve_date_range(date(2025, 1, 1), date(2025, 1, 31))
    assert start == date(2025, 1, 1)
    assert end == date(2025, 1, 31)
