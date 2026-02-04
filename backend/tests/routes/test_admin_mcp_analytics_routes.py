from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.principal import UserPrincipal
from app.routes.v1.admin.mcp import analytics as analytics_module
from app.schemas.admin_analytics import (
    AlertCategory,
    AlertSeverity,
    BookingFunnelPeriod,
    CategoryPerformancePeriod,
    CategorySortBy,
    CohortMetric,
    CohortPeriod,
    CohortUserType,
    FunnelSegmentBy,
    RevenueBreakdownBy,
    RevenueComparisonMode,
    RevenuePeriod,
    SupplyDemandPeriod,
)


async def _direct_to_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


class _ErrorWithHttp(Exception):
    def __init__(self, status_code: int, detail: str):
        self._status_code = status_code
        self._detail = detail

    def to_http_exception(self):
        return HTTPException(status_code=self._status_code, detail=self._detail)


def _principal() -> UserPrincipal:
    return UserPrincipal(user_id="admin", email="admin@example.com")


def test_handle_exception_branches():
    with pytest.raises(HTTPException) as exc:
        analytics_module._handle_exception(HTTPException(status_code=400, detail="bad"), "detail")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        analytics_module._handle_exception(_ErrorWithHttp(418, "teapot"), "detail")
    assert exc.value.status_code == 418

    with pytest.raises(HTTPException) as exc:
        analytics_module._handle_exception(RuntimeError("boom"), "detail")
    assert exc.value.detail == "detail"


@pytest.mark.asyncio
async def test_revenue_dashboard_route_success(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(revenue_dashboard=lambda **_kwargs: {"ok": True})
    result = await analytics_module.revenue_dashboard(
        period=RevenuePeriod.LAST_7_DAYS,
        compare_to=RevenueComparisonMode.PREVIOUS_PERIOD,
        breakdown_by=RevenueBreakdownBy.DAY,
        service=service,
        _=_principal(),
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_booking_funnel_route_success(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(booking_funnel=lambda **_kwargs: {"ok": True})
    result = await analytics_module.booking_funnel(
        period=BookingFunnelPeriod.LAST_7_DAYS,
        segment_by=FunnelSegmentBy.DEVICE,
        service=service,
        _=_principal(),
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_supply_demand_route_success(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(supply_demand=lambda **_kwargs: {"ok": True})
    result = await analytics_module.supply_demand(
        period=SupplyDemandPeriod.LAST_7_DAYS,
        location="Manhattan",
        category="music",
        service=service,
        _=_principal(),
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_category_performance_route_success(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(category_performance=lambda **_kwargs: {"ok": True})
    result = await analytics_module.category_performance(
        period=CategoryPerformancePeriod.LAST_7_DAYS,
        sort_by=CategorySortBy.REVENUE,
        limit=5,
        service=service,
        _=_principal(),
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_cohort_retention_route_success(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(cohort_retention=lambda **_kwargs: {"ok": True})
    result = await analytics_module.cohort_retention(
        user_type=CohortUserType.STUDENT,
        cohort_period=CohortPeriod.MONTH,
        periods_back=6,
        metric=CohortMetric.ACTIVE,
        service=service,
        _=_principal(),
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_platform_alerts_route_success(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)
    service = SimpleNamespace(platform_alerts=lambda **_kwargs: {"ok": True})
    result = await analytics_module.platform_alerts(
        severity=AlertSeverity.WARNING,
        category=AlertCategory.REVENUE,
        acknowledged=False,
        service=service,
        _=_principal(),
    )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_revenue_dashboard_route_error(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(revenue_dashboard=_boom)
    with pytest.raises(HTTPException):
        await analytics_module.revenue_dashboard(
            period=RevenuePeriod.LAST_7_DAYS,
            compare_to=None,
            breakdown_by=None,
            service=service,
            _=_principal(),
        )


@pytest.mark.asyncio
async def test_booking_funnel_route_error(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(booking_funnel=_boom)
    with pytest.raises(HTTPException):
        await analytics_module.booking_funnel(
            period=BookingFunnelPeriod.LAST_7_DAYS,
            segment_by=None,
            service=service,
            _=_principal(),
        )


@pytest.mark.asyncio
async def test_supply_demand_route_error(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(supply_demand=_boom)
    with pytest.raises(HTTPException):
        await analytics_module.supply_demand(
            period=SupplyDemandPeriod.LAST_7_DAYS,
            location=None,
            category=None,
            service=service,
            _=_principal(),
        )


@pytest.mark.asyncio
async def test_category_performance_route_error(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(category_performance=_boom)
    with pytest.raises(HTTPException):
        await analytics_module.category_performance(
            period=CategoryPerformancePeriod.LAST_7_DAYS,
            sort_by=CategorySortBy.REVENUE,
            limit=5,
            service=service,
            _=_principal(),
        )


@pytest.mark.asyncio
async def test_cohort_retention_route_error(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(cohort_retention=_boom)
    with pytest.raises(HTTPException):
        await analytics_module.cohort_retention(
            user_type=CohortUserType.STUDENT,
            cohort_period=CohortPeriod.MONTH,
            periods_back=6,
            metric=CohortMetric.ACTIVE,
            service=service,
            _=_principal(),
        )


@pytest.mark.asyncio
async def test_platform_alerts_route_error(monkeypatch):
    monkeypatch.setattr(analytics_module.asyncio, "to_thread", _direct_to_thread)

    def _boom(**_kwargs):
        raise HTTPException(status_code=400, detail="bad")

    service = SimpleNamespace(platform_alerts=_boom)
    with pytest.raises(HTTPException):
        await analytics_module.platform_alerts(
            severity=None,
            category=None,
            acknowledged=False,
            service=service,
            _=_principal(),
        )
