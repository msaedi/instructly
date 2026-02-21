"""Helper for creating fixed test accounts with services and availability."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.core.enums import RoleName
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.models.user import User
from app.services.permission_service import PermissionService

TZ = "America/New_York"
FIXED_STUDENT_EMAIL = "test.student@example.com"
FIXED_INSTRUCTOR_EMAIL = "test.instructor@example.com"
TEST_PASSWORD = "TestPassword123!"


def ensure_user(db: Session, email: str, role: str) -> User:
    """Ensure a user exists with the given email and role."""
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise ValueError("email is required")

    u = db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    ).scalar_one_or_none()
    if not u:
        u = User(
            email=normalized_email,
            hashed_password=get_password_hash(TEST_PASSWORD),
            first_name="Test",
            last_name=role.capitalize(),
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
            account_status="active",
            timezone=TZ,
        )
        db.add(u)
        try:
            db.flush()
        except IntegrityError:
            # Another test session may have inserted the same fixed account concurrently.
            db.rollback()
            u = db.execute(
                select(User).where(func.lower(User.email) == normalized_email)
            ).scalar_one_or_none()
            if not u:
                raise

    # Ensure role using PermissionService (idempotent if already assigned).
    permission_service = PermissionService(db)
    role_name = RoleName.STUDENT if role.lower() == "student" else RoleName.INSTRUCTOR
    permission_service.assign_role(u.id, role_name)
    if role.lower() == "student":
        from app.core.enums import PermissionName

        permission_service.grant_permission(u.id, PermissionName.CREATE_BOOKINGS.value)
    db.refresh(u)
    db.commit()

    return u


def ensure_instructor_profile_and_service(
    db: Session, instructor: User, svc_name: str = "Guitar", price: float = 120.00
):
    """Ensure instructor has profile and an active service."""
    from datetime import datetime, timezone

    prof = db.execute(
        select(InstructorProfile).where(InstructorProfile.user_id == instructor.id)
    ).scalar_one_or_none()

    if not prof:
        prof = InstructorProfile(
            user_id=instructor.id,
            bio="Test instructor",
            years_experience=5,
            bgc_status="passed",
            is_live=True,
            bgc_completed_at=datetime.now(timezone.utc),
            min_advance_booking_hours=2,
            buffer_time_minutes=15,
        )
        db.add(prof)
        db.flush()

    # Find or create catalog service
    svc = db.execute(
        select(ServiceCatalog).where(ServiceCatalog.name == svc_name)
    ).scalar_one_or_none()

    if not svc:
        # Try by slug
        slug = svc_name.lower()
        svc = db.execute(
            select(ServiceCatalog).where(ServiceCatalog.slug == slug)
        ).scalar_one_or_none()

    if not svc:
        # Create catalog service if it doesn't exist
        svc = ServiceCatalog(
            name=svc_name,
            slug=svc_name.lower(),
            description=f"Test {svc_name} service",
            is_active=True,
        )
        db.add(svc)
        db.flush()

    # Find or create instructor service link
    link = db.execute(
        select(InstructorService).where(
            InstructorService.instructor_profile_id == prof.id,
            InstructorService.service_catalog_id == svc.id,
        )
    ).scalar_one_or_none()

    if not link:
        link = InstructorService(
            instructor_profile_id=prof.id,
            service_catalog_id=svc.id,
            hourly_rate=price,
            duration_options=[60],
            offers_online=True,
            offers_travel=False,
            offers_at_location=False,
            is_active=True,
        )
        db.add(link)
        db.flush()

    db.commit()
    return prof, svc, link


def ensure_future_windows_via_api(client, monday: date, windows_by_date: Dict[str, List[Dict]], auth_headers: Dict[str, str] = None):
    """Seed availability windows via the bitmap /week API endpoint."""
    # Ensure monday is actually a Monday
    if monday.weekday() != 0:
        days_until_monday = (7 - monday.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = monday + timedelta(days=days_until_monday)

    payload = {
        "week_start": monday.isoformat(),
        "clear_existing": True,
        "schedule": [],
    }

    # Convert windows_by_date format to schedule format
    # Only include dates within the week starting at monday
    week_end = monday + timedelta(days=6)
    for date_str, windows in windows_by_date.items():
        try:
            date_obj = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            # Only include dates within the week
            if monday <= date_obj <= week_end:
                for window in windows:
                    payload["schedule"].append(
                        {
                            "date": date_str,
                            "start_time": window["start_time"],
                            "end_time": window["end_time"],
                        }
                    )
        except (ValueError, TypeError):
            # Skip invalid dates
            continue

    headers = auth_headers or {}
    r = client.post("/api/v1/instructors/availability/week", json=payload, headers=headers)
    assert r.status_code in (200, 304, 409), f"seeding windows failed: {r.status_code} {r.text}"


def next_monday(today: date | None = None) -> date:
    """Get the next Monday from today (or given date)."""
    today = today or date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7  # If today is Monday, get next Monday
    return today + timedelta(days=days_until_monday)
