from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from app.auth import get_password_hash
from app.core.enums import RoleName
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.search_event import SearchEvent
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.schemas.admin_analytics import (
    FunnelSnapshotComparison,
    FunnelSnapshotPeriod,
    FunnelSnapshotStage,
)
from app.services.funnel_analytics_service import (
    FunnelAnalyticsService,
    _build_deltas,
    _build_insights,
    _build_stage_models,
    _percentage,
    _resolve_comparison_period,
    _resolve_period,
    _shift_month,
)
from app.services.permission_service import PermissionService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_student(
    db,
    *,
    email: str,
    created_at: datetime,
    phone_verified: bool,
) -> User:
    student = User(
        email=email,
        hashed_password=get_password_hash("TestPassword123!"),
        first_name="Test",
        last_name="Student",
        phone="+12125551234",
        phone_verified=phone_verified,
        zip_code="10001",
        is_active=True,
        created_at=created_at,
    )
    db.add(student)
    db.flush()

    PermissionService(db).assign_role(student.id, RoleName.STUDENT)
    db.commit()
    return student


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


@pytest.mark.usefixtures("catalog_data")
def test_funnel_snapshot_builds_counts_and_insights(db, test_instructor):
    now = datetime.now(timezone.utc)
    service = FunnelAnalyticsService(db)
    start, end = _resolve_period(FunnelSnapshotPeriod.LAST_7_DAYS)
    baseline_signups = service.analytics_repo.count_users_created(
        start=start,
        end=end,
        role_name=RoleName.STUDENT.value,
    )
    baseline_verified = service.analytics_repo.count_users_created(
        start=start,
        end=end,
        role_name=RoleName.STUDENT.value,
        phone_verified=True,
    )
    baseline_search = service.analytics_repo.count_search_events(start=start, end=end)
    baseline_booking_started = service.analytics_repo.count_bookings(
        start=start,
        end=end,
        date_field="created_at",
    )
    baseline_booking_confirmed = service.analytics_repo.count_bookings(
        start=start,
        end=end,
        date_field="created_at",
        statuses=["CONFIRMED", "COMPLETED"],
    )
    baseline_completed = service.analytics_repo.count_bookings(
        start=start,
        end=end,
        date_field="created_at",
        statuses=["COMPLETED"],
    )
    _create_student(
        db,
        email="student-a@example.com",
        created_at=now - timedelta(days=1),
        phone_verified=True,
    )
    _create_student(
        db,
        email="student-b@example.com",
        created_at=now - timedelta(days=1),
        phone_verified=True,
    )
    student_c = _create_student(
        db,
        email="student-c@example.com",
        created_at=now - timedelta(days=1),
        phone_verified=False,
    )

    db.add(
        SearchEvent(
            search_query="guitar",
            search_type="natural_language",
            results_count=2,
            searched_at=now - timedelta(days=1),
        )
    )

    instructor_service = _instructor_service(db, test_instructor.id)
    create_booking_pg_safe(
        db,
        student_id=student_c.id,
        instructor_id=test_instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=now.date(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.COMPLETED,
        service_name="Lesson",
        hourly_rate=Decimal("50.00"),
        total_price=Decimal("50.00"),
        duration_minutes=60,
        created_at=now - timedelta(days=1),
    )
    db.flush()

    result = service.get_funnel_snapshot(
        period=FunnelSnapshotPeriod.LAST_7_DAYS,
        compare_to=None,
    )

    stage_map = {stage.stage: stage for stage in result.current_period.stages}
    assert stage_map["signup"].count - baseline_signups == 3
    assert stage_map["verified"].count - baseline_verified == 2
    assert stage_map["search"].count - baseline_search == 1
    assert stage_map["booking_started"].count - baseline_booking_started == 1
    assert stage_map["booking_confirmed"].count - baseline_booking_confirmed == 1
    assert stage_map["completed"].count - baseline_completed == 1
    assert stage_map["verified"].conversion_rate is not None
    assert any("Visits not tracked" in insight for insight in result.insights)
    assert any("Biggest drop-off" in insight for insight in result.insights)


def test_funnel_snapshot_skips_search_when_unavailable(db):
    now = datetime.now(timezone.utc)
    _create_student(
        db,
        email="student-d@example.com",
        created_at=now - timedelta(days=1),
        phone_verified=False,
    )

    service = FunnelAnalyticsService(db)

    def _raise():
        raise RuntimeError("search table missing")

    service.analytics_repo.count_search_events = _raise  # type: ignore[assignment]

    result = service.get_funnel_snapshot(
        period=FunnelSnapshotPeriod.LAST_7_DAYS,
        compare_to=None,
    )
    stage_names = [stage.stage for stage in result.current_period.stages]
    assert "search" not in stage_names
    assert any("Search events not tracked" in insight for insight in result.insights)


def test_helper_functions_and_deltas():
    assert _percentage(Decimal("1"), Decimal("0")) == Decimal("0")
    assert _percentage(Decimal("1"), Decimal("4")) == Decimal("25")

    start, end = _resolve_period(FunnelSnapshotPeriod.TODAY)
    assert start <= end
    _resolve_period(FunnelSnapshotPeriod.YESTERDAY)
    _resolve_period(FunnelSnapshotPeriod.LAST_7_DAYS)
    _resolve_period(FunnelSnapshotPeriod.LAST_30_DAYS)
    _resolve_period(FunnelSnapshotPeriod.THIS_MONTH)

    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    week_end = datetime.now(timezone.utc)
    _resolve_comparison_period(week_start, week_end, FunnelSnapshotComparison.PREVIOUS_PERIOD)
    _resolve_comparison_period(week_start, week_end, FunnelSnapshotComparison.SAME_PERIOD_LAST_WEEK)
    _resolve_comparison_period(week_start, week_end, FunnelSnapshotComparison.SAME_PERIOD_LAST_MONTH)
    _resolve_comparison_period(
        week_start,
        week_end,
        cast(FunnelSnapshotComparison, "unknown"),
    )

    shifted = _shift_month(datetime(2024, 3, 31, tzinfo=timezone.utc), -1)
    assert shifted.month == 2

    stages = _build_stage_models(
        [
            ("signup", 0),
            ("verified", 2),
            ("completed", 1),
        ]
    )
    assert stages[1].conversion_rate is None

    comparison = _build_stage_models([("signup", 0), ("verified", 1)])
    deltas = _build_deltas(stages, comparison)
    assert deltas["verified"] >= Decimal("0")

    insights = _build_insights(
        stages=[
            FunnelSnapshotStage(
                stage="signup",
                count=10,
            ),
            FunnelSnapshotStage(
                stage="completed",
                count=0,
                conversion_rate=Decimal("0"),
                drop_off_rate=Decimal("100"),
            ),
        ],
        overall_conversion=Decimal("0"),
        missing_stages=["visits"],
    )
    assert "Overall conversion below 1%" in insights
    assert any("Visits not tracked" in insight for insight in insights)

    empty_insights = _build_insights(
        stages=[],
        overall_conversion=Decimal("0"),
        missing_stages=[],
    )
    assert any("No funnel data available" in insight for insight in empty_insights)
