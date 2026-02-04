"""Funnel analytics service for user conversion snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_analytics import (
    FunnelSnapshotComparison,
    FunnelSnapshotPeriod,
    FunnelSnapshotPeriodData,
    FunnelSnapshotResponse,
    FunnelSnapshotStage,
)
from app.services.base import BaseService


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _resolve_period(period: FunnelSnapshotPeriod) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == FunnelSnapshotPeriod.TODAY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == FunnelSnapshotPeriod.YESTERDAY:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if period == FunnelSnapshotPeriod.LAST_7_DAYS:
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == FunnelSnapshotPeriod.LAST_30_DAYS:
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == FunnelSnapshotPeriod.THIS_MONTH:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _resolve_comparison_period(
    start: datetime, end: datetime, compare_to: FunnelSnapshotComparison
) -> tuple[datetime, datetime]:
    duration = end - start
    if compare_to == FunnelSnapshotComparison.PREVIOUS_PERIOD:
        return start - duration, start
    if compare_to == FunnelSnapshotComparison.SAME_PERIOD_LAST_WEEK:
        delta = timedelta(days=7)
        return start - delta, end - delta
    if compare_to == FunnelSnapshotComparison.SAME_PERIOD_LAST_MONTH:
        return _shift_month(start, -1), _shift_month(end, -1)
    return start - duration, start


def _shift_month(value: datetime, months: int) -> datetime:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return value.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    next_month = datetime(year, month, 28, tzinfo=timezone.utc) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day)).day


def _build_stage_models(items: list[tuple[str, int]]) -> list[FunnelSnapshotStage]:
    stages: list[FunnelSnapshotStage] = []
    for index, (name, count) in enumerate(items):
        conversion = None
        drop_off = None
        if index > 0:
            prev_count = items[index - 1][1]
            if prev_count > 0:
                conversion = _quantize(_percentage(Decimal(count), Decimal(prev_count)))
                drop_off = _quantize(Decimal("100") - conversion)
        stages.append(
            FunnelSnapshotStage(
                stage=name,
                count=count,
                conversion_rate=conversion,
                drop_off_rate=drop_off,
            )
        )
    return stages


def _find_biggest_drop_off(stages: list[FunnelSnapshotStage]) -> tuple[str, Decimal]:
    biggest = ""
    worst_rate = Decimal("0")
    for stage in stages:
        if stage.drop_off_rate is None:
            continue
        if stage.drop_off_rate > worst_rate:
            worst_rate = stage.drop_off_rate
            biggest = stage.stage
    return biggest, _quantize(worst_rate)


def _build_deltas(
    current: list[FunnelSnapshotStage],
    comparison: list[FunnelSnapshotStage],
) -> dict[str, Decimal]:
    comparison_counts = {stage.stage: stage.count for stage in comparison}
    deltas: dict[str, Decimal] = {}
    for stage in current:
        previous = comparison_counts.get(stage.stage, 0)
        if previous == 0:
            delta = Decimal("0") if stage.count == 0 else Decimal("100")
        else:
            delta = _percentage(Decimal(stage.count - previous), Decimal(previous))
        deltas[stage.stage] = _quantize(delta)
    return deltas


def _build_insights(
    *,
    stages: list[FunnelSnapshotStage],
    overall_conversion: Decimal,
    missing_stages: list[str],
) -> list[str]:
    insights: list[str] = []
    if "visits" in missing_stages:
        insights.append("Visits not tracked; funnel starts at signup.")
    if "search" in missing_stages:
        insights.append("Search events not tracked; search stage omitted.")
    biggest, drop_rate = _find_biggest_drop_off(stages)
    if biggest and drop_rate >= Decimal("30"):
        insights.append(f"Biggest drop-off at {biggest} ({drop_rate}% loss)")
    if overall_conversion < Decimal("1"):
        insights.append("Overall conversion below 1%")
    if not stages:
        insights.append("No funnel data available for period.")
    return insights


class FunnelAnalyticsService(BaseService):
    """Service for user conversion funnel snapshots."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.analytics_repo = RepositoryFactory.create_analytics_repository(db)

    @BaseService.measure_operation("admin.analytics.funnel_snapshot")
    def get_funnel_snapshot(
        self,
        *,
        period: FunnelSnapshotPeriod,
        compare_to: FunnelSnapshotComparison | None,
    ) -> FunnelSnapshotResponse:
        start, end = _resolve_period(period)
        current_data, missing = self._build_period_data(start=start, end=end)
        insights = _build_insights(
            stages=current_data.stages,
            overall_conversion=current_data.overall_conversion,
            missing_stages=missing,
        )

        comparison_data = None
        deltas = None
        if compare_to is not None:
            compare_start, compare_end = _resolve_comparison_period(start, end, compare_to)
            comparison_data, _ = self._build_period_data(start=compare_start, end=compare_end)
            deltas = _build_deltas(current_data.stages, comparison_data.stages)

        return FunnelSnapshotResponse(
            current_period=current_data,
            comparison_period=comparison_data,
            deltas=deltas,
            insights=insights,
        )

    def _optional_count(self, stage: str, getter: Callable[[], int]) -> int | None:
        try:
            return int(getter())
        except Exception as exc:
            self.logger.warning("Funnel stage %s unavailable: %s", stage, exc)
            return None

    def _build_period_data(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[FunnelSnapshotPeriodData, list[str]]:
        stages: list[tuple[str, int]] = []
        missing: list[str] = ["visits"]

        signups = self.analytics_repo.count_users_created(
            start=start,
            end=end,
            role_name=RoleName.STUDENT.value,
        )
        stages.append(("signup", signups))

        verified = self.analytics_repo.count_users_created(
            start=start,
            end=end,
            role_name=RoleName.STUDENT.value,
            phone_verified=True,
        )
        stages.append(("verified", verified))

        search_count = self._optional_count(
            "search",
            lambda: self.analytics_repo.count_search_events(start=start, end=end),
        )
        if search_count is None:
            missing.append("search")
        else:
            stages.append(("search", search_count))

        booking_started = self.analytics_repo.count_bookings(
            start=start,
            end=end,
            date_field="created_at",
        )
        stages.append(("booking_started", booking_started))

        booking_confirmed = self.analytics_repo.count_bookings(
            start=start,
            end=end,
            date_field="created_at",
            statuses=["CONFIRMED", "COMPLETED"],
        )
        stages.append(("booking_confirmed", booking_confirmed))

        completed = self.analytics_repo.count_bookings(
            start=start,
            end=end,
            date_field="created_at",
            statuses=["COMPLETED"],
        )
        stages.append(("completed", completed))

        stage_models = _build_stage_models(stages)
        overall = Decimal("0")
        if stage_models:
            first = stage_models[0].count
            last = stage_models[-1].count
            if first > 0:
                overall = _percentage(Decimal(last), Decimal(first))
        overall = _quantize(overall)

        return (
            FunnelSnapshotPeriodData(
                period_start=start,
                period_end=end,
                stages=stage_models,
                overall_conversion=overall,
            ),
            missing,
        )
