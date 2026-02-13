"""Platform analytics service for admin MCP tooling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from sqlalchemy.orm import Session

from app.repositories.analytics_repository import CategoryBookingRow
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_analytics import (
    Alert,
    AlertCategory,
    AlertSeverity,
    BalanceMetrics,
    BookingFunnel,
    BookingFunnelPeriod,
    CategoryMetrics,
    CategoryPerformance,
    CategoryPerformancePeriod,
    CategorySortBy,
    CohortData,
    CohortMetric,
    CohortPeriod,
    CohortRetention,
    CohortUserType,
    DemandMetrics,
    FunnelSegmentBy,
    FunnelStage,
    PlatformAlerts,
    RevenueBreakdownBy,
    RevenueComparison,
    RevenueComparisonMode,
    RevenueDashboard,
    RevenueHealth,
    RevenuePeriod,
    RevenuePeriodBreakdown,
    SupplyDemand,
    SupplyDemandPeriod,
    SupplyGap,
    SupplyMetrics,
    UnfulfilledSearch,
)
from app.services.base import BaseService
from app.utils.bitset import unpack_indexes

ALERT_THRESHOLDS = {
    "revenue_drop_pct": Decimal("20"),
    "revenue_drop_critical_pct": Decimal("30"),
    "refund_rate_pct": Decimal("10"),
    "payment_failure_rate_pct": Decimal("5"),
    "cancellation_rate_pct": Decimal("15"),
    "completion_rate_min_pct": Decimal("80"),
    "min_avg_rating": Decimal("4.5"),
    "review_response_rate_pct": Decimal("50"),
    "no_show_rate_pct": Decimal("2"),
    "zero_result_rate_pct": Decimal("30"),
}


@dataclass
class _BookingSummary:
    total: int
    completed: int
    cancelled: int
    gmv: Decimal
    instructor_payouts: Decimal


@dataclass
class _CategoryDemand:
    name: str
    demand: Decimal


@dataclass
class _CategoryAccumulator:
    category_id: str
    category_name: str
    bookings: int
    gmv: Decimal
    payouts: Decimal
    completed: int


class PlatformAnalyticsService(BaseService):
    """Service for platform analytics."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.analytics_repo = RepositoryFactory.create_analytics_repository(db)

    @BaseService.measure_operation("admin.analytics.revenue_dashboard")
    def revenue_dashboard(
        self,
        *,
        period: RevenuePeriod,
        compare_to: RevenueComparisonMode | None,
        breakdown_by: RevenueBreakdownBy | None,
    ) -> RevenueDashboard:
        start, end = _resolve_period(period)
        summary = self._summarize_bookings(start, end)
        platform_revenue = summary.gmv - summary.instructor_payouts
        net_revenue = platform_revenue
        take_rate = _percentage(platform_revenue, summary.gmv)
        completion_rate = _percentage(Decimal(summary.completed), Decimal(summary.total))
        avg_booking_value = _safe_div(summary.gmv, Decimal(summary.completed))

        comparison = None
        if compare_to is not None:
            compare_start, compare_end = _resolve_comparison_period(start, end, compare_to)
            compare_summary = self._summarize_bookings(compare_start, compare_end)
            compare_gmv = compare_summary.gmv
            compare_platform = compare_summary.gmv - compare_summary.instructor_payouts
            gmv_delta = summary.gmv - compare_gmv
            revenue_delta = platform_revenue - compare_platform
            comparison = RevenueComparison(
                period=compare_to.value,
                gmv=_quantize(compare_gmv),
                gmv_delta=_quantize(gmv_delta),
                gmv_delta_pct=_percentage(gmv_delta, compare_gmv),
                revenue_delta=_quantize(revenue_delta),
                revenue_delta_pct=_percentage(revenue_delta, compare_platform),
            )

        breakdown = None
        if breakdown_by is not None:
            breakdown = self._build_revenue_breakdown(start, end, breakdown_by)

        health = self._build_revenue_health(summary, comparison)

        return RevenueDashboard(
            period=period.value,
            period_start=start,
            period_end=end,
            gmv=_quantize(summary.gmv),
            platform_revenue=_quantize(platform_revenue),
            instructor_payouts=_quantize(summary.instructor_payouts),
            net_revenue=_quantize(net_revenue),
            take_rate=_quantize(take_rate),
            total_bookings=summary.total,
            completed_bookings=summary.completed,
            cancelled_bookings=summary.cancelled,
            completion_rate=_quantize(completion_rate),
            average_booking_value=_quantize(avg_booking_value),
            comparison=comparison,
            breakdown=breakdown,
            health=health,
        )

    @BaseService.measure_operation("admin.analytics.booking_funnel")
    def booking_funnel(
        self,
        *,
        period: BookingFunnelPeriod,
        segment_by: FunnelSegmentBy | None,
    ) -> BookingFunnel:
        start, end = _resolve_period(RevenuePeriod(period.value))
        search_count = self.analytics_repo.count_search_events(start=start, end=end)
        view_profile_count = self.analytics_repo.count_search_interactions(
            start=start, end=end, interaction_type="view_profile"
        )
        start_booking_count = self.analytics_repo.count_bookings(
            start=start, end=end, date_field="created_at"
        )
        payment_count = self.analytics_repo.count_payment_events(
            start=start,
            end=end,
            event_types=["auth_succeeded", "captured"],
        )
        confirmed_count = self.analytics_repo.count_bookings(
            start=start,
            end=end,
            date_field="created_at",
            statuses=["CONFIRMED", "COMPLETED"],
        )

        stages = _build_funnel_stages(
            [
                ("search", search_count),
                ("view_profile", view_profile_count),
                ("start_booking", start_booking_count),
                ("complete_payment", payment_count),
                ("booking_confirmed", confirmed_count),
            ]
        )

        overall_conversion = _percentage(Decimal(confirmed_count), Decimal(search_count))
        biggest_drop_off, drop_rate = _find_biggest_drop_off(stages)
        recommendations = _build_funnel_recommendations(biggest_drop_off, drop_rate)

        segments = None
        if segment_by is not None:
            segments = self._build_segmented_funnel(
                stages=stages,
                segment_by=segment_by,
                start=start,
                end=end,
            )

        return BookingFunnel(
            period=period.value,
            stages=stages,
            overall_conversion=_quantize(overall_conversion),
            biggest_drop_off=biggest_drop_off,
            drop_off_rate=_quantize(drop_rate),
            segments=segments,
            recommendations=recommendations,
        )

    @BaseService.measure_operation("admin.analytics.supply_demand")
    def supply_demand(
        self,
        *,
        period: SupplyDemandPeriod,
        location: str | None,
        category: str | None,
    ) -> SupplyDemand:
        start, end = _resolve_period(RevenuePeriod(period.value))
        category_ids = self.analytics_repo.resolve_category_ids(category)
        region_ids = self.analytics_repo.resolve_region_ids(location)
        instructor_ids = self.analytics_repo.list_active_instructor_ids(
            category_ids=category_ids or None,
            region_ids=region_ids or None,
        )
        availability_hours = self._availability_hours(
            instructor_ids=instructor_ids,
            start=start,
            end=end,
        )
        active_instructors = len(instructor_ids)
        avg_availability = _safe_div(availability_hours, Decimal(active_instructors))
        new_instructors = self.analytics_repo.count_instructors_created(
            start=start,
            end=end,
            category_ids=category_ids or None,
            region_ids=region_ids or None,
        )
        churned_instructors = self.analytics_repo.count_instructors_churned(
            start=start,
            end=end,
            category_ids=category_ids or None,
            region_ids=region_ids or None,
        )

        total_searches = self.analytics_repo.count_search_events(start=start, end=end)
        unique_searchers = self.analytics_repo.count_unique_searchers(start=start, end=end)
        booking_attempts = self.analytics_repo.count_bookings(
            start=start,
            end=end,
            date_field="created_at",
            instructor_ids=instructor_ids or None,
        )
        successful_bookings = self.analytics_repo.count_bookings(
            start=start,
            end=end,
            date_field="created_at",
            instructor_ids=instructor_ids or None,
            statuses=["CONFIRMED", "COMPLETED"],
        )
        unfulfilled_searches = self.analytics_repo.count_search_events_zero_results(
            start=start, end=end
        )

        booked_minutes = self.analytics_repo.sum_booking_duration_minutes(
            start=start,
            end=end,
            statuses=["COMPLETED"],
            instructor_ids=instructor_ids or None,
        )
        booked_hours = Decimal(booked_minutes) / Decimal("60")
        supply_utilization = _safe_div(booked_hours, availability_hours)
        demand_fulfillment = _safe_div(Decimal(successful_bookings), Decimal(booking_attempts))
        supply_demand_ratio = _safe_div(Decimal(active_instructors), Decimal(booking_attempts))
        balance_status = _balance_status(supply_demand_ratio)

        gaps = self._build_supply_gaps(start, end, location)
        top_unfulfilled = self._build_top_unfulfilled(start, end)

        return SupplyDemand(
            period=period.value,
            filters_applied={
                **({"location": location} if location else {}),
                **({"category": category} if category else {}),
            },
            supply=SupplyMetrics(
                active_instructors=active_instructors,
                total_availability_hours=_quantize(availability_hours),
                avg_availability_per_instructor=_quantize(avg_availability),
                new_instructors=new_instructors,
                churned_instructors=churned_instructors,
            ),
            demand=DemandMetrics(
                total_searches=total_searches,
                unique_searchers=unique_searchers,
                booking_attempts=booking_attempts,
                successful_bookings=successful_bookings,
                unfulfilled_searches=unfulfilled_searches,
            ),
            balance=BalanceMetrics(
                supply_utilization=_quantize(supply_utilization),
                demand_fulfillment=_quantize(demand_fulfillment),
                supply_demand_ratio=_quantize(supply_demand_ratio),
                status=balance_status,
            ),
            gaps=gaps,
            top_unfulfilled=top_unfulfilled,
        )

    @BaseService.measure_operation("admin.analytics.category_performance")
    def category_performance(
        self,
        *,
        period: CategoryPerformancePeriod,
        sort_by: CategorySortBy,
        limit: int,
    ) -> CategoryPerformance:
        start, end = _resolve_category_period(period)
        previous_start, previous_end = _resolve_previous_period(start, end)
        current_rows = self.analytics_repo.list_category_booking_rows(start=start, end=end)
        previous_rows = self.analytics_repo.list_category_booking_rows(
            start=previous_start, end=previous_end
        )
        review_ratings = self._category_review_ratings(start, end)

        current_metrics = self._build_category_metrics(current_rows, review_ratings, start, end)
        previous_metrics = self._build_category_metrics(
            previous_rows, {}, previous_start, previous_end
        )
        metrics_with_growth = []
        for metric in current_metrics.values():
            prev = previous_metrics.get(metric.category_id)
            prev_gmv = prev.gmv if prev else Decimal("0")
            growth_pct = _percentage(metric.gmv - prev_gmv, prev_gmv)
            metric = metric.model_copy(update={"growth_pct": _quantize(growth_pct)})
            metrics_with_growth.append(metric)

        metrics_sorted = _sort_category_metrics(metrics_with_growth, sort_by)
        metrics_sorted = metrics_sorted[: max(limit, 0) or len(metrics_sorted)]
        metrics_sorted = _apply_rank_changes(metrics_sorted, previous_metrics, sort_by)

        top_growing = max(metrics_sorted, key=lambda item: item.growth_pct, default=None)
        top_revenue = max(metrics_sorted, key=lambda item: item.revenue, default=None)
        needs_attention = [
            metric
            for metric in metrics_sorted
            if metric.conversion_rate < Decimal("50") or metric.growth_pct < Decimal("0")
        ]
        insights = _build_category_insights(top_growing, top_revenue, needs_attention)

        return CategoryPerformance(
            period=period.value,
            categories=metrics_sorted,
            top_growing=top_growing,
            top_revenue=top_revenue,
            needs_attention=needs_attention,
            insights=insights,
        )

    @BaseService.measure_operation("admin.analytics.cohort_retention")
    def cohort_retention(
        self,
        *,
        user_type: CohortUserType,
        cohort_period: CohortPeriod,
        periods_back: int,
        metric: CohortMetric,
    ) -> CohortRetention:
        now = datetime.now(timezone.utc)
        period_start = _start_of_period(now, cohort_period)
        cohorts: list[CohortData] = []
        for offset in range(periods_back):
            start = _shift_period(period_start, cohort_period, -offset)
            end = _shift_period(start, cohort_period, 1)
            users = self.analytics_repo.list_users_created_between(
                role_name=user_type.value,
                start=start,
                end=end,
            )
            user_ids = [user.id for user in users]
            retention = []
            for period_index in range(periods_back):
                period_start_idx = _shift_period(start, cohort_period, period_index)
                period_end_idx = _shift_period(start, cohort_period, period_index + 1)
                retained = self.analytics_repo.list_user_ids_with_bookings(
                    user_ids=user_ids,
                    role=user_type.value,
                    start=period_start_idx,
                    end=period_end_idx,
                )
                retention.append(_percentage(Decimal(len(retained)), Decimal(len(user_ids))))
            cohorts.append(
                CohortData(
                    cohort_label=_format_cohort_label(start, cohort_period),
                    cohort_size=len(user_ids),
                    retention=[_quantize(value) for value in retention],
                )
            )

        avg_retention = _average_retention(cohorts)
        benchmark = _benchmark_label(avg_retention)
        insights = _cohort_insights(avg_retention)

        return CohortRetention(
            user_type=user_type.value,
            metric=metric.value,
            cohorts=cohorts,
            avg_retention={key: _quantize(value) for key, value in avg_retention.items()},
            benchmark_comparison=benchmark,
            insights=insights,
        )

    @BaseService.measure_operation("admin.analytics.platform_alerts")
    def platform_alerts(
        self,
        *,
        severity: AlertSeverity | None,
        category: AlertCategory | None,
        acknowledged: bool,
    ) -> PlatformAlerts:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)

        alerts = []
        alerts.extend(self._revenue_alerts(today_start, now, week_start))
        alerts.extend(self._operations_alerts(week_start, now))
        alerts.extend(self._quality_alerts(month_start, now))
        alerts.extend(self._technical_alerts(week_start, now))

        if severity is not None:
            alerts = [alert for alert in alerts if alert.severity == severity.value]
        if category is not None:
            alerts = [alert for alert in alerts if alert.category == category.value]
        if acknowledged:
            alerts = alerts

        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for alert in alerts:
            by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1
            by_category[alert.category] = by_category.get(alert.category, 0) + 1

        return PlatformAlerts(
            total_active=len(alerts),
            alerts=alerts,
            by_severity=by_severity,
            by_category=by_category,
        )

    def _summarize_bookings(self, start: datetime, end: datetime) -> _BookingSummary:
        bookings = self.analytics_repo.list_bookings_by_start(start=start, end=end)
        total = len(bookings)
        completed = 0
        cancelled = 0
        gmv = Decimal("0")
        payout_cents = 0
        for booking in bookings:
            status = (booking.status or "").upper()
            if status == "COMPLETED":
                completed += 1
                gmv += _decimal(booking.total_price)
                pd = booking.payment_detail
                payout_cents += int((pd.instructor_payout_amount if pd else None) or 0)
            elif status == "CANCELLED":
                cancelled += 1
        instructor_payouts = Decimal(payout_cents) / Decimal("100")
        return _BookingSummary(
            total=total,
            completed=completed,
            cancelled=cancelled,
            gmv=gmv,
            instructor_payouts=instructor_payouts,
        )

    def _build_revenue_breakdown(
        self, start: datetime, end: datetime, breakdown_by: RevenueBreakdownBy
    ) -> list[RevenuePeriodBreakdown]:
        if breakdown_by == RevenueBreakdownBy.CATEGORY:
            rows = self.analytics_repo.list_category_booking_rows(start=start, end=end)
            bucket: dict[str, dict[str, Decimal | int]] = {}
            for row in rows:
                entry = bucket.setdefault(
                    row.category_name,
                    {"gmv": Decimal("0"), "revenue": Decimal("0"), "bookings": 0},
                )
                entry["bookings"] = int(entry["bookings"]) + 1
                if row.status.upper() == "COMPLETED":
                    gmv = _decimal(row.total_price)
                    payout = Decimal(int(row.instructor_payout_amount or 0)) / Decimal("100")
                    entry["gmv"] = Decimal(entry["gmv"]) + gmv
                    entry["revenue"] = Decimal(entry["revenue"]) + (gmv - payout)
            return [
                RevenuePeriodBreakdown(
                    period_label=label,
                    gmv=_quantize(Decimal(values["gmv"])),
                    revenue=_quantize(Decimal(values["revenue"])),
                    bookings=int(values["bookings"]),
                )
                for label, values in bucket.items()
            ]

        bookings = self.analytics_repo.list_bookings_by_start(start=start, end=end)
        buckets: dict[str, dict[str, Decimal | int]] = {}
        for booking in bookings:
            timestamp = booking.booking_start_utc
            if breakdown_by == RevenueBreakdownBy.WEEK:
                period_label = _week_label(timestamp)
            else:
                period_label = timestamp.date().isoformat()
            entry = buckets.setdefault(
                period_label,
                {"gmv": Decimal("0"), "revenue": Decimal("0"), "bookings": 0},
            )
            entry["bookings"] = int(entry["bookings"]) + 1
            if (booking.status or "").upper() == "COMPLETED":
                gmv = _decimal(booking.total_price)
                pd = booking.payment_detail
                payout = Decimal(int((pd.instructor_payout_amount if pd else None) or 0)) / Decimal(
                    "100"
                )
                entry["gmv"] = Decimal(entry["gmv"]) + gmv
                entry["revenue"] = Decimal(entry["revenue"]) + (gmv - payout)

        return [
            RevenuePeriodBreakdown(
                period_label=label,
                gmv=_quantize(Decimal(values["gmv"])),
                revenue=_quantize(Decimal(values["revenue"])),
                bookings=int(values["bookings"]),
            )
            for label, values in sorted(buckets.items())
        ]

    def _build_revenue_health(
        self, summary: _BookingSummary, comparison: RevenueComparison | None
    ) -> RevenueHealth:
        alerts: list[str] = []
        status = "healthy"
        if comparison is not None:
            if comparison.gmv_delta_pct <= -ALERT_THRESHOLDS["revenue_drop_critical_pct"]:
                alerts.append("Revenue down more than 30% vs comparison")
                status = "critical"
            elif comparison.gmv_delta_pct <= -ALERT_THRESHOLDS["revenue_drop_pct"]:
                alerts.append("Revenue down more than 20% vs comparison")
                status = "warning"

        if summary.completed == 0:
            alerts.append("No completed bookings in period")
            status = "warning" if status == "healthy" else status

        return RevenueHealth(status=status, alerts=alerts)

    def _availability_hours(
        self, *, instructor_ids: list[str], start: datetime, end: datetime
    ) -> Decimal:
        days = self.analytics_repo.list_availability_days(
            instructor_ids=instructor_ids,
            start_date=start.date(),
            end_date=end.date(),
        )
        slots = 0
        for day in days:
            bits = day.bits or b""
            if bits:
                slots += len(unpack_indexes(bits))
        return Decimal(slots) * Decimal("0.5")

    def _build_supply_gaps(
        self, start: datetime, end: datetime, location: str | None
    ) -> list[SupplyGap]:
        rows = self.analytics_repo.list_category_booking_rows(start=start, end=end)
        category_counts: dict[str, _CategoryDemand] = {}
        for row in rows:
            entry = category_counts.get(row.category_id)
            if entry is None:
                entry = _CategoryDemand(name=row.category_name, demand=Decimal("0"))
                category_counts[row.category_id] = entry
            entry.demand += Decimal("1")
        gaps: list[SupplyGap] = []
        for category_id, values in category_counts.items():
            demand_score = values.demand
            supply_score = Decimal(self.analytics_repo.count_instructors_for_category(category_id))
            priority = _gap_priority(demand_score, supply_score)
            gaps.append(
                SupplyGap(
                    category=values.name,
                    location=location,
                    demand_score=_quantize(demand_score),
                    supply_score=_quantize(supply_score),
                    priority=priority,
                )
            )
        return gaps

    def _build_top_unfulfilled(self, start: datetime, end: datetime) -> list[UnfulfilledSearch]:
        rows = self.analytics_repo.list_top_unfulfilled_searches(start=start, end=end)
        return [
            UnfulfilledSearch(query=query, count=count, closest_match=None) for query, count in rows
        ]

    def _build_segmented_funnel(
        self,
        *,
        stages: list[FunnelStage],
        segment_by: FunnelSegmentBy,
        start: datetime,
        end: datetime,
    ) -> dict[str, list[FunnelStage]]:
        total_search = stages[0].count if stages else 0
        segment_counts = self.analytics_repo.get_search_event_segment_counts(
            start=start, end=end, segment_by=segment_by.value
        )
        segments: dict[str, list[FunnelStage]] = {}
        for segment, count in segment_counts.items():
            ratio = Decimal(count) / Decimal(total_search) if total_search else Decimal("0")
            segment_stage_counts = []
            for stage in stages:
                stage_count = int((Decimal(stage.count) * ratio).quantize(Decimal("1")))
                segment_stage_counts.append((stage.stage, stage_count))
            segments[segment] = _build_funnel_stages(segment_stage_counts)
        return segments

    def _category_review_ratings(self, start: datetime, end: datetime) -> dict[str, Decimal]:
        rows = self.analytics_repo.list_category_booking_rows(start=start, end=end)
        category_ids = {row.category_id for row in rows}
        ratings: dict[str, Decimal] = {cid: Decimal("0") for cid in category_ids}
        counts: dict[str, int] = {cid: 0 for cid in category_ids}
        # Use reviews directly when possible
        avg_rating = self.analytics_repo.avg_review_rating(start=start, end=end)
        for category_id in category_ids:
            ratings[category_id] = Decimal(str(avg_rating))
            counts[category_id] = 1 if avg_rating else 0
        result: dict[str, Decimal] = {}
        for category_id in category_ids:
            if counts[category_id]:
                result[category_id] = ratings[category_id]
            else:
                result[category_id] = Decimal("0")
        return result

    def _build_category_metrics(
        self,
        rows: list[CategoryBookingRow],
        review_ratings: dict[str, Decimal],
        start: datetime,
        end: datetime,
    ) -> dict[str, CategoryMetrics]:
        metrics: dict[str, _CategoryAccumulator] = {}
        student_counts: dict[str, dict[str, int]] = {}
        for row in rows:
            entry = metrics.get(row.category_id)
            if entry is None:
                entry = _CategoryAccumulator(
                    category_id=row.category_id,
                    category_name=row.category_name,
                    bookings=0,
                    gmv=Decimal("0"),
                    payouts=Decimal("0"),
                    completed=0,
                )
                metrics[row.category_id] = entry
            entry.bookings += 1
            if row.status.upper() == "COMPLETED":
                entry.completed += 1
                gmv = _decimal(row.total_price)
                payout = Decimal(int(row.instructor_payout_amount or 0)) / Decimal("100")
                entry.gmv += gmv
                entry.payouts += payout
            student_counts.setdefault(row.category_id, {})[row.student_id] = (
                student_counts.get(row.category_id, {}).get(row.student_id, 0) + 1
            )

        results: dict[str, CategoryMetrics] = {}
        for category_id, values in metrics.items():
            gmv = values.gmv
            payouts = values.payouts
            revenue = gmv - payouts
            bookings = values.bookings
            completed = values.completed
            avg_price = _safe_div(gmv, Decimal(bookings))
            conversion_rate = _percentage(Decimal(completed), Decimal(bookings))
            students = student_counts.get(category_id, {})
            repeaters = len([count for count in students.values() if count > 1])
            repeat_rate = _percentage(Decimal(repeaters), Decimal(len(students)))
            instructor_count = self.analytics_repo.count_instructors_for_category(category_id)
            student_count = self.analytics_repo.count_students_for_category(
                start=start,
                end=end,
                category_id=category_id,
            )
            avg_rating = review_ratings.get(category_id, Decimal("0"))
            results[category_id] = CategoryMetrics(
                category_id=category_id,
                category_name=values.category_name,
                bookings=bookings,
                revenue=_quantize(revenue),
                gmv=_quantize(gmv),
                avg_price=_quantize(avg_price),
                avg_rating=_quantize(avg_rating),
                instructor_count=instructor_count,
                student_count=student_count,
                conversion_rate=_quantize(conversion_rate),
                repeat_rate=_quantize(repeat_rate),
                growth_pct=Decimal("0"),
                rank_change=0,
            )
        return results

    def _revenue_alerts(
        self, today_start: datetime, now: datetime, week_start: datetime
    ) -> list[Alert]:
        today_summary = self._summarize_bookings(today_start, now)
        week_summary = self._summarize_bookings(week_start, now)
        avg_daily_gmv = _safe_div(week_summary.gmv, Decimal("7"))
        alerts: list[Alert] = []
        if avg_daily_gmv > 0:
            drop_pct = _percentage(today_summary.gmv - avg_daily_gmv, avg_daily_gmv)
            if drop_pct <= -ALERT_THRESHOLDS["revenue_drop_pct"]:
                severity = (
                    AlertSeverity.CRITICAL
                    if drop_pct <= -ALERT_THRESHOLDS["revenue_drop_critical_pct"]
                    else AlertSeverity.WARNING
                )
                alerts.append(
                    _build_alert(
                        severity=severity,
                        category=AlertCategory.REVENUE,
                        title="Daily revenue decline",
                        description="Daily revenue down versus 7-day average",
                        metric_name="daily_revenue",
                        current_value=today_summary.gmv,
                        threshold_value=avg_daily_gmv,
                        recommended_action="Review acquisition channels and payment funnel.",
                    )
                )

        refunded = self.analytics_repo.count_refunded_bookings(start=week_start, end=now)
        total_bookings = self.analytics_repo.count_bookings(
            start=week_start, end=now, date_field="booking_start_utc"
        )
        refund_rate = _percentage(Decimal(refunded), Decimal(total_bookings))
        if refund_rate > ALERT_THRESHOLDS["refund_rate_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.REVENUE,
                    title="Refund rate elevated",
                    description="Refund rate exceeds 10%",
                    metric_name="refund_rate",
                    current_value=refund_rate,
                    threshold_value=ALERT_THRESHOLDS["refund_rate_pct"],
                    recommended_action="Audit refund drivers and dispute handling.",
                )
            )

        failures = self.analytics_repo.count_payment_events(
            start=week_start, end=now, event_types=["auth_failed", "capture_failed"]
        )
        total_events = self.analytics_repo.count_payment_events(
            start=week_start,
            end=now,
            event_types=["auth_failed", "auth_succeeded", "captured", "capture_failed"],
        )
        failure_rate = _percentage(Decimal(failures), Decimal(total_events))
        if failure_rate > ALERT_THRESHOLDS["payment_failure_rate_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.REVENUE,
                    title="Payment failure rate high",
                    description="Payment failures exceed 5%",
                    metric_name="payment_failure_rate",
                    current_value=failure_rate,
                    threshold_value=ALERT_THRESHOLDS["payment_failure_rate_pct"],
                    recommended_action="Inspect payment provider status and retry flows.",
                )
            )
        return alerts

    def _operations_alerts(self, start: datetime, end: datetime) -> list[Alert]:
        alerts: list[Alert] = []
        total = self.analytics_repo.count_bookings(
            start=start, end=end, date_field="booking_start_utc"
        )
        cancelled = self.analytics_repo.count_bookings(
            start=start, end=end, date_field="booking_start_utc", statuses=["CANCELLED"]
        )
        completed = self.analytics_repo.count_bookings(
            start=start, end=end, date_field="booking_start_utc", statuses=["COMPLETED"]
        )
        cancellation_rate = _percentage(Decimal(cancelled), Decimal(total))
        completion_rate = _percentage(Decimal(completed), Decimal(total))

        if cancellation_rate > ALERT_THRESHOLDS["cancellation_rate_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.OPERATIONS,
                    title="Cancellation rate high",
                    description="Cancellation rate exceeds 15%",
                    metric_name="cancellation_rate",
                    current_value=cancellation_rate,
                    threshold_value=ALERT_THRESHOLDS["cancellation_rate_pct"],
                    recommended_action="Review cancellation reasons and messaging.",
                )
            )
        if completion_rate < ALERT_THRESHOLDS["completion_rate_min_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.OPERATIONS,
                    title="Completion rate low",
                    description="Booking completion below 80%",
                    metric_name="completion_rate",
                    current_value=completion_rate,
                    threshold_value=ALERT_THRESHOLDS["completion_rate_min_pct"],
                    recommended_action="Investigate instructor or payment failures.",
                )
            )
        return alerts

    def _quality_alerts(self, start: datetime, end: datetime) -> list[Alert]:
        alerts: list[Alert] = []
        avg_rating = Decimal(str(self.analytics_repo.avg_review_rating(start=start, end=end)))
        if avg_rating and avg_rating < ALERT_THRESHOLDS["min_avg_rating"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.QUALITY,
                    title="Average rating dropped",
                    description="Average rating below 4.5",
                    metric_name="avg_rating",
                    current_value=avg_rating,
                    threshold_value=ALERT_THRESHOLDS["min_avg_rating"],
                    recommended_action="Review quality feedback and instructor coaching.",
                )
            )

        review_count = self.analytics_repo.count_reviews(start=start, end=end)
        response_count = self.analytics_repo.count_review_responses(start=start, end=end)
        response_rate = _percentage(Decimal(response_count), Decimal(review_count))
        if response_rate < ALERT_THRESHOLDS["review_response_rate_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.QUALITY,
                    title="Review response rate low",
                    description="Review response rate below 50%",
                    metric_name="review_response_rate",
                    current_value=response_rate,
                    threshold_value=ALERT_THRESHOLDS["review_response_rate_pct"],
                    recommended_action="Encourage instructors to respond to reviews.",
                )
            )

        no_show_count = self.analytics_repo.count_no_show_bookings(start=start, end=end)
        total = self.analytics_repo.count_bookings(
            start=start, end=end, date_field="booking_start_utc"
        )
        no_show_rate = _percentage(Decimal(no_show_count), Decimal(total))
        if no_show_rate > ALERT_THRESHOLDS["no_show_rate_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.QUALITY,
                    title="Instructor no-show rate high",
                    description="No-show rate exceeds 2%",
                    metric_name="no_show_rate",
                    current_value=no_show_rate,
                    threshold_value=ALERT_THRESHOLDS["no_show_rate_pct"],
                    recommended_action="Investigate instructor reliability issues.",
                )
            )
        return alerts

    def _technical_alerts(self, start: datetime, end: datetime) -> list[Alert]:
        alerts: list[Alert] = []
        total_searches = self.analytics_repo.count_search_events(start=start, end=end)
        zero_results = self.analytics_repo.count_search_events_zero_results(start=start, end=end)
        zero_rate = _percentage(Decimal(zero_results), Decimal(total_searches))
        if zero_rate > ALERT_THRESHOLDS["zero_result_rate_pct"]:
            alerts.append(
                _build_alert(
                    severity=AlertSeverity.WARNING,
                    category=AlertCategory.TECHNICAL,
                    title="Search zero-result rate high",
                    description="Zero-result rate exceeds 30%",
                    metric_name="zero_result_rate",
                    current_value=zero_rate,
                    threshold_value=ALERT_THRESHOLDS["zero_result_rate_pct"],
                    recommended_action="Review search relevance and catalog coverage.",
                )
            )
        return alerts


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _safe_div(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _resolve_period(period: RevenuePeriod) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == RevenuePeriod.TODAY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == RevenuePeriod.YESTERDAY:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if period == RevenuePeriod.LAST_7_DAYS:
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == RevenuePeriod.LAST_30_DAYS:
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == RevenuePeriod.THIS_MONTH:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if period == RevenuePeriod.LAST_MONTH:
        start = _shift_month(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), -1)
        end = _shift_month(start, 1)
        return start, end
    if period == RevenuePeriod.THIS_QUARTER:
        quarter_start_month = 3 * ((now.month - 1) // 3) + 1
        start = datetime(now.year, quarter_start_month, 1, tzinfo=timezone.utc)
        return start, now
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _resolve_category_period(period: CategoryPerformancePeriod) -> tuple[datetime, datetime]:
    if period == CategoryPerformancePeriod.LAST_QUARTER:
        now = datetime.now(timezone.utc)
        current_quarter_start_month = 3 * ((now.month - 1) // 3) + 1
        current_quarter_start = datetime(
            now.year, current_quarter_start_month, 1, tzinfo=timezone.utc
        )
        last_quarter_end = current_quarter_start
        last_quarter_start = _shift_month(last_quarter_end, -3)
        return last_quarter_start, last_quarter_end
    return _resolve_period(RevenuePeriod(period.value))


def _resolve_previous_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    duration = end - start
    return start - duration, start


def _resolve_comparison_period(
    start: datetime, end: datetime, compare_to: RevenueComparisonMode
) -> tuple[datetime, datetime]:
    duration = end - start
    if compare_to == RevenueComparisonMode.PREVIOUS_PERIOD:
        return start - duration, start
    if compare_to == RevenueComparisonMode.SAME_PERIOD_LAST_MONTH:
        return _shift_month(start, -1), _shift_month(end, -1)
    if compare_to == RevenueComparisonMode.SAME_PERIOD_LAST_YEAR:
        return start.replace(year=start.year - 1), end.replace(year=end.year - 1)
    return start - duration, start


def _shift_month(value: datetime, months: int) -> datetime:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return value.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    next_month = datetime(year, month, 28, tzinfo=timezone.utc) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day)).day


def _build_funnel_stages(items: list[tuple[str, int]]) -> list[FunnelStage]:
    stages: list[FunnelStage] = []
    for index, (name, count) in enumerate(items):
        conversion = None
        if index < len(items) - 1:
            next_count = items[index + 1][1]
            conversion = _percentage(Decimal(next_count), Decimal(count))
            conversion = _quantize(conversion)
        stages.append(FunnelStage(stage=name, count=count, conversion_to_next=conversion))
    return stages


def _find_biggest_drop_off(stages: list[FunnelStage]) -> tuple[str, Decimal]:
    biggest = ""
    worst_rate = Decimal("0")
    for stage in stages:
        if stage.conversion_to_next is None:
            continue
        drop_rate = Decimal("100") - stage.conversion_to_next
        if drop_rate > worst_rate:
            worst_rate = drop_rate
            biggest = stage.stage
    return biggest or (stages[0].stage if stages else ""), _quantize(worst_rate)


def _build_funnel_recommendations(biggest_drop_off: str, drop_rate: Decimal) -> list[str]:
    if not biggest_drop_off:
        return []
    return [
        f"Biggest drop-off at {biggest_drop_off} stage ({drop_rate}% drop)",
    ]


def _balance_status(ratio: Decimal) -> str:
    if ratio <= Decimal("0"):
        return "undersupply"
    if ratio < Decimal("0.8"):
        return "undersupply"
    if ratio > Decimal("1.2"):
        return "oversupply"
    return "balanced"


def _gap_priority(demand: Decimal, supply: Decimal) -> str:
    if supply <= 0:
        return "high"
    ratio = demand / supply
    if ratio >= Decimal("2"):
        return "high"
    if ratio >= Decimal("1"):
        return "medium"
    return "low"


def _week_label(timestamp: datetime) -> str:
    week_start = timestamp - timedelta(days=timestamp.weekday())
    return week_start.date().isoformat()


def _sort_category_metrics(
    metrics: list[CategoryMetrics], sort_by: CategorySortBy
) -> list[CategoryMetrics]:
    if sort_by == CategorySortBy.BOOKINGS:
        return sorted(metrics, key=lambda item: item.bookings, reverse=True)
    if sort_by == CategorySortBy.GROWTH:
        return sorted(metrics, key=lambda item: item.growth_pct, reverse=True)
    if sort_by == CategorySortBy.CONVERSION:
        return sorted(metrics, key=lambda item: item.conversion_rate, reverse=True)
    return sorted(metrics, key=lambda item: item.revenue, reverse=True)


def _apply_rank_changes(
    current: list[CategoryMetrics],
    previous: dict[str, CategoryMetrics],
    sort_by: CategorySortBy,
) -> list[CategoryMetrics]:
    prev_sorted = _sort_category_metrics(list(previous.values()), sort_by)
    prev_ranks = {metric.category_id: idx + 1 for idx, metric in enumerate(prev_sorted)}
    updated: list[CategoryMetrics] = []
    for idx, metric in enumerate(current):
        prev_rank = prev_ranks.get(metric.category_id)
        rank_change = (prev_rank - (idx + 1)) if prev_rank else 0
        updated.append(metric.model_copy(update={"rank_change": rank_change}))
    return updated


def _build_category_insights(
    top_growing: CategoryMetrics | None,
    top_revenue: CategoryMetrics | None,
    needs_attention: list[CategoryMetrics],
) -> list[str]:
    insights: list[str] = []
    if top_growing:
        insights.append(f"{top_growing.category_name} leads growth at {top_growing.growth_pct}%.")
    if top_revenue:
        insights.append(f"{top_revenue.category_name} drives top revenue.")
    if needs_attention:
        insights.append("Some categories need attention due to low conversion or decline.")
    return insights


def _start_of_period(value: datetime, period: CohortPeriod) -> datetime:
    if period == CohortPeriod.WEEK:
        start = value - timedelta(days=value.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_period(value: datetime, period: CohortPeriod, offset: int) -> datetime:
    if period == CohortPeriod.WEEK:
        return value + timedelta(weeks=offset)
    return _shift_month(value, offset)


def _format_cohort_label(value: datetime, period: CohortPeriod) -> str:
    if period == CohortPeriod.WEEK:
        return value.strftime("%Y-%m-%d")
    return value.strftime("%b %Y")


def _average_retention(cohorts: list[CohortData]) -> dict[int, Decimal]:
    totals: dict[int, Decimal] = {}
    counts: dict[int, int] = {}
    for cohort in cohorts:
        for idx, value in enumerate(cohort.retention):
            totals[idx] = totals.get(idx, Decimal("0")) + value
            counts[idx] = counts.get(idx, 0) + 1
    return {
        idx: (totals[idx] / Decimal(counts[idx])) if counts[idx] else Decimal("0") for idx in totals
    }


def _benchmark_label(avg_retention: dict[int, Decimal]) -> str:
    if not avg_retention:
        return "No data"
    month_two = avg_retention.get(1, Decimal("0"))
    if month_two >= Decimal("60"):
        return "Above average"
    if month_two >= Decimal("40"):
        return "Average"
    return "Below average"


def _cohort_insights(avg_retention: dict[int, Decimal]) -> list[str]:
    if not avg_retention:
        return []
    first = avg_retention.get(0, Decimal("0"))
    second = avg_retention.get(1, Decimal("0"))
    drop = first - second
    if drop > Decimal("30"):
        return ["Early retention drop-off exceeds 30%."]
    return ["Retention is within expected range."]


def _build_alert(
    *,
    severity: AlertSeverity,
    category: AlertCategory,
    title: str,
    description: str,
    metric_name: str,
    current_value: Decimal,
    threshold_value: Decimal,
    recommended_action: str | None,
) -> Alert:
    return Alert(
        id=str(uuid.uuid4()),
        severity=severity.value,
        category=category.value,
        title=title,
        description=description,
        metric_name=metric_name,
        current_value=_quantize(_decimal(current_value)),
        threshold_value=_quantize(_decimal(threshold_value)),
        triggered_at=datetime.now(timezone.utc),
        recommended_action=recommended_action,
    )
