from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from app.models.availability_day import AvailabilityDay
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentEvent
from app.models.review import Review
from app.models.search_event import SearchEvent
from app.models.search_interaction import SearchInteraction
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.repositories.analytics_repository import CategoryBookingRow
from app.schemas.admin_analytics import (
    Alert,
    AlertCategory,
    AlertSeverity,
    BookingFunnelPeriod,
    CategoryMetrics,
    CategoryPerformancePeriod,
    CategorySortBy,
    CohortData,
    CohortMetric,
    CohortPeriod,
    CohortUserType,
    FunnelSegmentBy,
    RevenueBreakdownBy,
    RevenueComparison,
    RevenueComparisonMode,
    RevenuePeriod,
    SupplyDemandPeriod,
)
from app.services.platform_analytics_service import (
    PlatformAnalyticsService,
    _average_retention,
    _balance_status,
    _benchmark_label,
    _BookingSummary,
    _build_category_insights,
    _build_funnel_recommendations,
    _cohort_insights,
    _decimal,
    _find_biggest_drop_off,
    _gap_priority,
    _percentage,
    _resolve_category_period,
    _resolve_comparison_period,
    _resolve_period,
    _safe_div,
    _sort_category_metrics,
    _week_label,
)

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _service(db) -> PlatformAnalyticsService:
    return PlatformAnalyticsService(db)


def _instructor_service(db, instructor_id: str) -> InstructorService:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise AssertionError("Missing instructor profile")
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == profile.id)
        .first()
    )
    if not service:
        raise AssertionError("Missing instructor service")
    return service


def _extra_service(db, instructor_id: str) -> InstructorService:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise AssertionError("Missing instructor profile")
    existing = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == profile.id)
        .first()
    )
    if not existing:
        raise AssertionError("Missing existing service")
    existing_catalog = (
        db.query(ServiceCatalog)
        .filter(ServiceCatalog.id == existing.service_catalog_id)
        .first()
    )
    # Find a catalog entry in a different subcategory
    catalog = (
        db.query(ServiceCatalog)
        .filter(ServiceCatalog.subcategory_id != existing_catalog.subcategory_id)
        .first()
    )
    if not catalog:
        catalog = existing_catalog
    new_service = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=Decimal("80.00"),
        is_active=True,
    )
    db.add(new_service)
    db.flush()
    return new_service


def _make_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: datetime,
    status: BookingStatus,
    total_price: Decimal,
    payout_cents: int | None = None,
    refund_cents: int | None = None,
) -> None:
    create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date.date(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=status,
        service_name="Lesson",
        hourly_rate=total_price,
        total_price=total_price,
        duration_minutes=60,
        instructor_payout_amount=payout_cents,
        refunded_to_card_amount=refund_cents,
    )
    db.flush()


@pytest.mark.usefixtures("catalog_data")
def test_revenue_dashboard_with_breakdown_and_comparison(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=1),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("100.00"),
        payout_cents=8000,
    )
    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=1),
        status=BookingStatus.CANCELLED,
        total_price=Decimal("50.00"),
        payout_cents=None,
        refund_cents=1000,
    )
    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=10),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("200.00"),
        payout_cents=15000,
    )

    result = service.revenue_dashboard(
        period=RevenuePeriod.LAST_7_DAYS,
        compare_to=RevenueComparisonMode.PREVIOUS_PERIOD,
        breakdown_by=RevenueBreakdownBy.DAY,
    )
    assert result.total_bookings == 2
    assert result.completed_bookings == 1
    assert result.gmv == Decimal("100.00")
    assert result.platform_revenue == Decimal("20.00")
    assert result.comparison is not None
    assert result.breakdown is not None

    category_breakdown = service.revenue_dashboard(
        period=RevenuePeriod.LAST_7_DAYS,
        compare_to=None,
        breakdown_by=RevenueBreakdownBy.CATEGORY,
    )
    assert category_breakdown.breakdown is not None
    assert category_breakdown.comparison is None


@pytest.mark.usefixtures("catalog_data")
def test_booking_funnel_with_segments(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    search_event = SearchEvent(
        search_query="guitar",
        search_type="natural_language",
        results_count=3,
        searched_at=now - timedelta(days=1),
        device_type="mobile",
    )
    db.add(search_event)
    db.flush()

    db.add(
        SearchEvent(
            search_query="piano",
            search_type="natural_language",
            results_count=0,
            searched_at=now - timedelta(days=1),
            device_type="desktop",
        )
    )
    db.add(
        SearchInteraction(
            search_event_id=search_event.id,
            interaction_type="view_profile",
            created_at=now - timedelta(days=1),
        )
    )

    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now.date(),
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.CONFIRMED,
        service_name="Lesson",
        hourly_rate=Decimal("75.00"),
        total_price=Decimal("75.00"),
        duration_minutes=60,
    )
    db.flush()
    db.add(
        PaymentEvent(
            booking_id=booking.id,
            event_type="auth_succeeded",
            created_at=now - timedelta(hours=1),
        )
    )

    result = service.booking_funnel(
        period=BookingFunnelPeriod.LAST_7_DAYS,
        segment_by=FunnelSegmentBy.DEVICE,
    )
    assert result.stages[0].stage == "search"
    assert result.segments is not None
    assert "mobile" in result.segments


@pytest.mark.usefixtures("catalog_data")
def test_supply_demand_with_filters(db, test_student, test_instructor_with_availability):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor_with_availability.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=2),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("120.00"),
        payout_cents=9000,
    )

    db.add(
        SearchEvent(
            search_query="math",
            search_type="natural_language",
            results_count=0,
            searched_at=now - timedelta(days=1),
            device_type="mobile",
        )
    )

    result = service.supply_demand(
        period=SupplyDemandPeriod.LAST_7_DAYS,
        location="Manhattan",
        category="music",
    )
    assert result.supply.active_instructors >= 1
    assert result.demand.total_searches >= 1
    assert result.balance.status in {"balanced", "oversupply", "undersupply"}


@pytest.mark.usefixtures("catalog_data")
def test_category_performance_last_quarter(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)
    extra_service = _extra_service(db, test_instructor.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=3),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("150.00"),
        payout_cents=10000,
    )
    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=extra_service.id,
        booking_date=now - timedelta(days=3),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("90.00"),
        payout_cents=6000,
    )

    review_booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now.date(),
        start_time=time(14, 0),
        end_time=time(15, 0),
        status=BookingStatus.COMPLETED,
        service_name="Lesson",
        hourly_rate=Decimal("60.00"),
        total_price=Decimal("60.00"),
        duration_minutes=60,
    )
    db.flush()
    db.add(
        Review(
            booking_id=review_booking.id,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service.id,
            rating=4,
            booking_completed_at=now,
        )
    )

    result = service.category_performance(
        period=CategoryPerformancePeriod.LAST_7_DAYS,
        sort_by=CategorySortBy.REVENUE,
        limit=10,
    )
    assert result.categories
    assert result.top_revenue is not None

    last_quarter = service.category_performance(
        period=CategoryPerformancePeriod.LAST_QUARTER,
        sort_by=CategorySortBy.BOOKINGS,
        limit=5,
    )
    assert last_quarter.categories is not None


@pytest.mark.usefixtures("catalog_data")
def test_cohort_retention_student_and_instructor(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    test_student.created_at = now - timedelta(days=45)
    test_instructor.created_at = now - timedelta(days=45)
    db.flush()

    instructor_service = _instructor_service(db, test_instructor.id)
    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=30),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("75.00"),
        payout_cents=5000,
    )

    student_retention = service.cohort_retention(
        user_type=CohortUserType.STUDENT,
        cohort_period=CohortPeriod.MONTH,
        periods_back=2,
        metric=CohortMetric.ACTIVE,
    )
    assert student_retention.cohorts

    instructor_retention = service.cohort_retention(
        user_type=CohortUserType.INSTRUCTOR,
        cohort_period=CohortPeriod.WEEK,
        periods_back=1,
        metric=CohortMetric.BOOKING,
    )
    assert instructor_retention.cohorts


@pytest.mark.usefixtures("catalog_data")
def test_platform_alerts_filters(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=2),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("100.00"),
        payout_cents=7000,
    )
    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=1),
        status=BookingStatus.CANCELLED,
        total_price=Decimal("50.00"),
        payout_cents=None,
        refund_cents=1000,
    )
    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=1),
        status=BookingStatus.NO_SHOW,
        total_price=Decimal("50.00"),
        payout_cents=None,
    )

    db.add(
        SearchEvent(
            search_query="zero",
            search_type="natural_language",
            results_count=0,
            searched_at=now - timedelta(days=1),
            device_type="mobile",
        )
    )
    db.add(
        Review(
            booking_id=create_booking_pg_safe(
                db,
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=instructor_service.id,
                booking_date=now.date(),
                start_time=time(16, 0),
                end_time=time(17, 0),
                status=BookingStatus.COMPLETED,
                service_name="Lesson",
                hourly_rate=Decimal("60.00"),
                total_price=Decimal("60.00"),
                duration_minutes=60,
            ).id,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service.id,
            rating=4,
            booking_completed_at=now,
        )
    )
    db.flush()

    alert = service.platform_alerts(
        severity=None,
        category=None,
        acknowledged=False,
    )
    assert alert.total_active >= 1

    filtered = service.platform_alerts(
        severity=AlertSeverity.WARNING,
        category=None,
        acknowledged=False,
    )
    assert all(item.severity == "warning" for item in filtered.alerts)


@pytest.mark.usefixtures("catalog_data")
def test_revenue_dashboard_without_breakdown(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=2),
        status=BookingStatus.CANCELLED,
        total_price=Decimal("55.00"),
        payout_cents=None,
    )

    result = service.revenue_dashboard(
        period=RevenuePeriod.LAST_7_DAYS,
        compare_to=None,
        breakdown_by=None,
    )
    assert result.breakdown is None
    assert result.comparison is None
    assert result.health.status == "warning"


@pytest.mark.usefixtures("catalog_data")
def test_revenue_dashboard_week_breakdown(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=1),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("120.00"),
        payout_cents=9000,
    )

    result = service.revenue_dashboard(
        period=RevenuePeriod.LAST_7_DAYS,
        compare_to=None,
        breakdown_by=RevenueBreakdownBy.WEEK,
    )
    assert result.breakdown
    assert result.breakdown[0].period_label


def test_booking_funnel_without_segments(db):
    service = _service(db)

    result = service.booking_funnel(
        period=BookingFunnelPeriod.LAST_7_DAYS,
        segment_by=None,
    )
    assert result.segments is None
    assert result.stages


def test_availability_hours_empty_bits(db, test_instructor):
    service = _service(db)
    today = datetime.now(timezone.utc).date()
    db.add(
        AvailabilityDay(
            instructor_id=test_instructor.id,
            day_date=today,
            bits=b"",
        )
    )
    db.flush()

    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    hours = service._availability_hours(
        instructor_ids=[test_instructor.id],
        start=start,
        end=end,
    )
    assert hours == Decimal("0")


@pytest.mark.usefixtures("catalog_data")
def test_category_review_ratings_without_reviews(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    _make_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now - timedelta(days=1),
        status=BookingStatus.COMPLETED,
        total_price=Decimal("75.00"),
        payout_cents=5000,
    )

    ratings = service._category_review_ratings(
        start=now - timedelta(days=2),
        end=now + timedelta(days=1),
    )
    assert ratings
    assert all(value == Decimal("0") for value in ratings.values())


@pytest.mark.usefixtures("catalog_data")
def test_category_review_ratings_with_review(db, test_student, test_instructor):
    service = _service(db)
    now = datetime.now(timezone.utc)
    instructor_service = _instructor_service(db, test_instructor.id)

    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now.date(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        status=BookingStatus.COMPLETED,
        service_name="Lesson",
        hourly_rate=Decimal("90.00"),
        total_price=Decimal("90.00"),
        duration_minutes=60,
    )
    db.flush()
    db.add(
        Review(
            booking_id=booking.id,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=instructor_service.id,
            rating=5,
            booking_completed_at=now,
        )
    )
    db.flush()

    ratings = service._category_review_ratings(
        start=now - timedelta(days=1),
        end=now + timedelta(days=1),
    )
    assert ratings
    assert all(value > Decimal("0") for value in ratings.values())


def test_build_category_metrics_handles_cancelled(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    rows = [
        CategoryBookingRow(
            booking_id="b1",
            category_id="cat-1",
            category_name="Music",
            status="COMPLETED",
            total_price=Decimal("100.00"),
            instructor_payout_amount=8000,
            student_id="s1",
            instructor_id="i1",
        ),
        CategoryBookingRow(
            booking_id="b2",
            category_id="cat-1",
            category_name="Music",
            status="CANCELLED",
            total_price=Decimal("40.00"),
            instructor_payout_amount=None,
            student_id="s1",
            instructor_id="i1",
        ),
    ]
    monkeypatch.setattr(
        service.analytics_repo,
        "count_instructors_for_category",
        lambda category_id: 2,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_students_for_category",
        lambda **kwargs: 3,
    )

    metrics = service._build_category_metrics(
        rows,
        {"cat-1": Decimal("4.3")},
        start=now - timedelta(days=1),
        end=now + timedelta(days=1),
    )
    metric = metrics["cat-1"]
    assert metric.bookings == 2
    assert metric.gmv == Decimal("100.00")
    assert metric.conversion_rate <= Decimal("100.00")


def test_supply_gaps_accumulates_categories(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    rows = [
        CategoryBookingRow(
            booking_id="b1",
            category_id="cat-1",
            category_name="Music",
            status="COMPLETED",
            total_price=Decimal("50.00"),
            instructor_payout_amount=4000,
            student_id="s1",
            instructor_id="i1",
        ),
        CategoryBookingRow(
            booking_id="b2",
            category_id="cat-1",
            category_name="Music",
            status="COMPLETED",
            total_price=Decimal("70.00"),
            instructor_payout_amount=5000,
            student_id="s2",
            instructor_id="i2",
        ),
    ]
    monkeypatch.setattr(
        service.analytics_repo,
        "list_category_booking_rows",
        lambda **kwargs: rows,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_instructors_for_category",
        lambda _category_id: 1,
    )

    gaps = service._build_supply_gaps(now - timedelta(days=1), now, None)
    assert gaps


def test_revenue_alerts_warning_and_rate_alerts(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    def fake_summary(start, end):
        if start == today_start:
            gmv = Decimal("75.00")
        else:
            gmv = Decimal("700.00")
        return _BookingSummary(
            total=7,
            completed=7,
            cancelled=0,
            gmv=gmv,
            instructor_payouts=Decimal("0"),
        )

    monkeypatch.setattr(service, "_summarize_bookings", fake_summary)
    monkeypatch.setattr(
        service.analytics_repo,
        "count_refunded_bookings",
        lambda **kwargs: 2,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_bookings",
        lambda **kwargs: 10,
    )

    def fake_payment_events(*, event_types, **kwargs):
        if set(event_types) == {"auth_failed", "capture_failed"}:
            return 3
        return 20

    monkeypatch.setattr(service.analytics_repo, "count_payment_events", fake_payment_events)

    alerts = service._revenue_alerts(today_start, now, week_start)
    assert any(alert.title == "Daily revenue decline" for alert in alerts)
    assert any(alert.metric_name == "refund_rate" for alert in alerts)
    assert any(alert.metric_name == "payment_failure_rate" for alert in alerts)


def test_revenue_alerts_critical(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    def fake_summary(start, end):
        if start == today_start:
            gmv = Decimal("0")
        else:
            gmv = Decimal("700.00")
        return _BookingSummary(
            total=7,
            completed=7,
            cancelled=0,
            gmv=gmv,
            instructor_payouts=Decimal("0"),
        )

    monkeypatch.setattr(service, "_summarize_bookings", fake_summary)
    monkeypatch.setattr(
        service.analytics_repo,
        "count_refunded_bookings",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_bookings",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_payment_events",
        lambda **kwargs: 0,
    )

    alerts = service._revenue_alerts(today_start, now, week_start)
    assert any(alert.severity == AlertSeverity.CRITICAL.value for alert in alerts)


def test_revenue_alerts_no_average(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    def fake_summary(start, end):
        return _BookingSummary(
            total=0,
            completed=0,
            cancelled=0,
            gmv=Decimal("0"),
            instructor_payouts=Decimal("0"),
        )

    monkeypatch.setattr(service, "_summarize_bookings", fake_summary)
    monkeypatch.setattr(
        service.analytics_repo,
        "count_refunded_bookings",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_bookings",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_payment_events",
        lambda **kwargs: 0,
    )

    alerts = service._revenue_alerts(today_start, now, week_start)
    assert alerts == []


def test_revenue_alerts_no_decline(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    def fake_summary(start, end):
        if start == today_start:
            gmv = Decimal("120.00")
        else:
            gmv = Decimal("700.00")
        return _BookingSummary(
            total=7,
            completed=7,
            cancelled=0,
            gmv=gmv,
            instructor_payouts=Decimal("0"),
        )

    monkeypatch.setattr(service, "_summarize_bookings", fake_summary)
    monkeypatch.setattr(
        service.analytics_repo,
        "count_refunded_bookings",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_bookings",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        service.analytics_repo,
        "count_payment_events",
        lambda **kwargs: 0,
    )

    alerts = service._revenue_alerts(today_start, now, week_start)
    assert all(alert.title != "Daily revenue decline" for alert in alerts)


def test_operations_quality_and_technical_alerts(monkeypatch, db):
    service = _service(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)

    def fake_count_bookings(*, statuses=None, **kwargs):
        if statuses == ["CANCELLED"]:
            return 20
        if statuses == ["COMPLETED"]:
            return 50
        return 100

    monkeypatch.setattr(service.analytics_repo, "count_bookings", fake_count_bookings)
    ops_alerts = service._operations_alerts(start, end)
    assert any(alert.metric_name == "cancellation_rate" for alert in ops_alerts)
    assert any(alert.metric_name == "completion_rate" for alert in ops_alerts)

    monkeypatch.setattr(service.analytics_repo, "avg_review_rating", lambda **kwargs: 4.0)
    monkeypatch.setattr(service.analytics_repo, "count_reviews", lambda **kwargs: 10)
    monkeypatch.setattr(service.analytics_repo, "count_review_responses", lambda **kwargs: 2)
    monkeypatch.setattr(service.analytics_repo, "count_no_show_bookings", lambda **kwargs: 3)
    monkeypatch.setattr(service.analytics_repo, "count_bookings", lambda **kwargs: 50)

    quality_alerts = service._quality_alerts(start, end)
    assert any(alert.metric_name == "avg_rating" for alert in quality_alerts)
    assert any(alert.metric_name == "review_response_rate" for alert in quality_alerts)
    assert any(alert.metric_name == "no_show_rate" for alert in quality_alerts)

    monkeypatch.setattr(service.analytics_repo, "count_search_events", lambda **kwargs: 10)
    monkeypatch.setattr(
        service.analytics_repo,
        "count_search_events_zero_results",
        lambda **kwargs: 4,
    )
    tech_alerts = service._technical_alerts(start, end)
    assert any(alert.metric_name == "zero_result_rate" for alert in tech_alerts)


def test_operations_alerts_no_issues(monkeypatch, db):
    service = _service(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)

    def fake_count_bookings(*, statuses=None, **kwargs):
        if statuses == ["CANCELLED"]:
            return 0
        if statuses == ["COMPLETED"]:
            return 90
        return 100

    monkeypatch.setattr(service.analytics_repo, "count_bookings", fake_count_bookings)
    alerts = service._operations_alerts(start, end)
    assert alerts == []


def test_quality_alerts_no_issues(monkeypatch, db):
    service = _service(db)
    start = datetime.now(timezone.utc) - timedelta(days=30)
    end = datetime.now(timezone.utc)

    monkeypatch.setattr(service.analytics_repo, "avg_review_rating", lambda **kwargs: 5.0)
    monkeypatch.setattr(service.analytics_repo, "count_reviews", lambda **kwargs: 10)
    monkeypatch.setattr(service.analytics_repo, "count_review_responses", lambda **kwargs: 10)
    monkeypatch.setattr(service.analytics_repo, "count_no_show_bookings", lambda **kwargs: 0)
    monkeypatch.setattr(service.analytics_repo, "count_bookings", lambda **kwargs: 10)

    alerts = service._quality_alerts(start, end)
    assert alerts == []


def test_technical_alerts_no_issues(monkeypatch, db):
    service = _service(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)

    monkeypatch.setattr(service.analytics_repo, "count_search_events", lambda **kwargs: 10)
    monkeypatch.setattr(
        service.analytics_repo,
        "count_search_events_zero_results",
        lambda **kwargs: 1,
    )

    alerts = service._technical_alerts(start, end)
    assert alerts == []


def test_platform_alerts_category_filter_acknowledged(monkeypatch, db):
    service = _service(db)
    now = datetime.now(timezone.utc)
    sample_alert = Alert(
        id="alert-1",
        severity=AlertSeverity.WARNING.value,
        category=AlertCategory.REVENUE.value,
        title="Test alert",
        description="Test description",
        metric_name="metric",
        current_value=Decimal("1"),
        threshold_value=Decimal("2"),
        triggered_at=now,
    )

    monkeypatch.setattr(service, "_revenue_alerts", lambda *args, **kwargs: [sample_alert])
    monkeypatch.setattr(service, "_operations_alerts", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "_quality_alerts", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "_technical_alerts", lambda *args, **kwargs: [])

    result = service.platform_alerts(
        severity=None,
        category=AlertCategory.REVENUE,
        acknowledged=True,
    )
    assert result.total_active == 1
    assert result.alerts[0].category == AlertCategory.REVENUE.value
    assert result.alerts[0].triggered_at.tzinfo is not None


def test_revenue_health_warning_and_critical(db):
    service = _service(db)
    summary = _BookingSummary(
        total=1,
        completed=1,
        cancelled=0,
        gmv=Decimal("100"),
        instructor_payouts=Decimal("0"),
    )
    warning_comp = RevenueComparison(
        period="previous_period",
        gmv=Decimal("100"),
        gmv_delta=Decimal("-25"),
        gmv_delta_pct=Decimal("-25"),
        revenue_delta=Decimal("-20"),
        revenue_delta_pct=Decimal("-20"),
    )
    critical_comp = RevenueComparison(
        period="previous_period",
        gmv=Decimal("100"),
        gmv_delta=Decimal("-35"),
        gmv_delta_pct=Decimal("-35"),
        revenue_delta=Decimal("-30"),
        revenue_delta_pct=Decimal("-30"),
    )
    ok_comp = RevenueComparison(
        period="previous_period",
        gmv=Decimal("100"),
        gmv_delta=Decimal("5"),
        gmv_delta_pct=Decimal("5"),
        revenue_delta=Decimal("5"),
        revenue_delta_pct=Decimal("5"),
    )

    ok = service._build_revenue_health(summary, ok_comp)
    assert ok.status == "healthy"

    warning = service._build_revenue_health(summary, warning_comp)
    assert warning.status == "warning"

    critical = service._build_revenue_health(summary, critical_comp)
    assert critical.status == "critical"

    no_completed = service._build_revenue_health(
        _BookingSummary(
            total=1,
            completed=0,
            cancelled=1,
            gmv=Decimal("0"),
            instructor_payouts=Decimal("0"),
        ),
        comparison=None,
    )
    assert "No completed bookings in period" in no_completed.alerts
    assert no_completed.status == "warning"

    critical_no_completed = service._build_revenue_health(
        _BookingSummary(
            total=1,
            completed=0,
            cancelled=1,
            gmv=Decimal("0"),
            instructor_payouts=Decimal("0"),
        ),
        comparison=critical_comp,
    )
    assert critical_no_completed.status == "critical"


def test_helper_functions_and_periods():
    assert _decimal(Decimal("1.5")) == Decimal("1.5")
    assert _decimal(None) == Decimal("0")
    assert _decimal("2.5") == Decimal("2.5")
    assert _safe_div(Decimal("1"), Decimal("0")) == Decimal("0")
    assert _percentage(Decimal("1"), Decimal("0")) == Decimal("0")
    assert _percentage(Decimal("1"), Decimal("4")) == Decimal("25")

    start, end = _resolve_period(RevenuePeriod.TODAY)
    assert start <= end
    _resolve_period(RevenuePeriod.YESTERDAY)
    _resolve_period(RevenuePeriod.LAST_7_DAYS)
    _resolve_period(RevenuePeriod.LAST_30_DAYS)
    _resolve_period(RevenuePeriod.THIS_MONTH)
    _resolve_period(RevenuePeriod.LAST_MONTH)
    _resolve_period(RevenuePeriod.THIS_QUARTER)
    _resolve_period(cast(RevenuePeriod, "unknown"))

    cat_start, cat_end = _resolve_category_period(CategoryPerformancePeriod.LAST_30_DAYS)
    assert cat_start <= cat_end


def test_helper_comparison_and_balance_logic():
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)

    _resolve_comparison_period(start, end, RevenueComparisonMode.PREVIOUS_PERIOD)
    _resolve_comparison_period(start, end, RevenueComparisonMode.SAME_PERIOD_LAST_MONTH)
    _resolve_comparison_period(start, end, RevenueComparisonMode.SAME_PERIOD_LAST_YEAR)
    _resolve_comparison_period(start, end, cast(RevenueComparisonMode, "unknown"))

    assert _balance_status(Decimal("-1")) == "undersupply"
    assert _balance_status(Decimal("0.5")) == "undersupply"
    assert _balance_status(Decimal("1.5")) == "oversupply"
    assert _balance_status(Decimal("1.0")) == "balanced"

    assert _gap_priority(Decimal("10"), Decimal("0")) == "high"
    assert _gap_priority(Decimal("10"), Decimal("4")) == "high"
    assert _gap_priority(Decimal("10"), Decimal("10")) == "medium"
    assert _gap_priority(Decimal("10"), Decimal("20")) == "low"

    label = _week_label(datetime(2024, 1, 3, tzinfo=timezone.utc))
    assert label.startswith("2024")


def test_helper_category_sorting_and_insights():
    metric_a = CategoryMetrics(
        category_id="a",
        category_name="A",
        bookings=5,
        revenue=Decimal("10"),
        gmv=Decimal("10"),
        avg_price=Decimal("2"),
        avg_rating=Decimal("4.5"),
        instructor_count=1,
        student_count=1,
        conversion_rate=Decimal("70"),
        repeat_rate=Decimal("0"),
        growth_pct=Decimal("20"),
        rank_change=0,
    )
    metric_b = CategoryMetrics(
        category_id="b",
        category_name="B",
        bookings=3,
        revenue=Decimal("8"),
        gmv=Decimal("8"),
        avg_price=Decimal("2"),
        avg_rating=Decimal("4.0"),
        instructor_count=1,
        student_count=1,
        conversion_rate=Decimal("40"),
        repeat_rate=Decimal("0"),
        growth_pct=Decimal("10"),
        rank_change=0,
    )

    sorted_growth = _sort_category_metrics([metric_a, metric_b], CategorySortBy.GROWTH)
    assert sorted_growth[0].category_id == "a"
    sorted_conversion = _sort_category_metrics([metric_a, metric_b], CategorySortBy.CONVERSION)
    assert sorted_conversion[0].category_id == "a"

    insights = _build_category_insights(metric_a, metric_b, [metric_b])
    assert insights


def test_helper_cohort_and_funnel_helpers():
    cohorts = [
        CohortData(
            cohort_label="Jan 2024",
            cohort_size=10,
            retention=[Decimal("100"), Decimal("50")],
        ),
        CohortData(
            cohort_label="Feb 2024",
            cohort_size=10,
            retention=[Decimal("100"), Decimal("70")],
        ),
    ]
    avg = _average_retention(cohorts)
    assert avg[1] == Decimal("60")

    assert _benchmark_label({}) == "No data"
    assert _benchmark_label({1: Decimal("65")}) == "Above average"
    assert _benchmark_label({1: Decimal("45")}) == "Average"
    assert _benchmark_label({1: Decimal("20")}) == "Below average"

    assert _cohort_insights({}) == []
    assert _cohort_insights({0: Decimal("100"), 1: Decimal("80")}) == [
        "Retention is within expected range."
    ]
    assert _cohort_insights({0: Decimal("100"), 1: Decimal("40")}) == [
        "Early retention drop-off exceeds 30%."
    ]

    biggest, drop = _find_biggest_drop_off([])
    assert biggest == ""
    assert drop == Decimal("0.00")
    assert _build_funnel_recommendations("", Decimal("0")) == []
