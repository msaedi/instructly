from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest

from app.core.enums import RoleName
from app.core.exceptions import BusinessRuleException
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService


def _create_instructor(db, *, email: str, status: str, is_live: bool | None = None) -> InstructorProfile:
    user = User(
        email=email,
        hashed_password="hashed",
        first_name="Test",
        last_name="Instructor",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    if is_live is None:
        is_live = status == "passed"

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = status
    profile.is_live = is_live
    profile.bgc_completed_at = (
        datetime.now(timezone.utc) if status == "passed" else None
    )
    db.add(profile)
    db.flush()

    db.commit()
    db.refresh(profile)
    return profile


def test_instructor_listing_filters_in_production(monkeypatch, db):
    monkeypatch.setenv("SITE_MODE", "production")

    passed_profile = _create_instructor(db, email="passed@example.com", status="passed")
    _create_instructor(db, email="pending@example.com", status="pending")

    service = InstructorService(db)

    list_result = service.get_all_instructors()
    assert all(entry["id"] == passed_profile.id for entry in list_result)

def test_instructor_listing_excludes_non_verified_in_all_modes(monkeypatch, db):
    monkeypatch.setenv("SITE_MODE", "local")

    passed_profile = _create_instructor(db, email="passed@example.com", status="passed")
    pending_profile = _create_instructor(db, email="pending@example.com", status="pending")

    service = InstructorService(db)

    list_result = service.get_all_instructors()
    ids = {entry["id"] for entry in list_result}
    assert ids == {passed_profile.id}
    assert pending_profile.id not in ids


@pytest.mark.asyncio
async def test_booking_blocked_for_unverified_in_production(monkeypatch, db):
    monkeypatch.setenv("SITE_MODE", "production")

    instructor_profile = _create_instructor(
        db, email="instructor@example.com", status="pending"
    )

    stub_service = SimpleNamespace(
        instructor_profile_id=instructor_profile.id,
        duration_options=[30],
    )

    class StubConflictRepository:
        def get_active_service(self, _service_id):
            return stub_service

        def get_instructor_profile(self, _instructor_id):
            return instructor_profile

    booking_service = BookingService(
        db,
        conflict_checker_repository=StubConflictRepository(),
    )

    student = SimpleNamespace(
        id="student1",
        roles=[SimpleNamespace(name=RoleName.STUDENT)],
    )

    booking_data = BookingCreate(
        instructor_id=instructor_profile.user_id,
        instructor_service_id="service1",
        booking_date=date.today(),
        start_time=time(9, 0),
        selected_duration=30,
    )

    with pytest.raises(BusinessRuleException):
        await booking_service._validate_booking_prerequisites(student, booking_data)


@pytest.mark.asyncio
async def test_booking_allows_unverified_in_non_production(monkeypatch, db):
    monkeypatch.setenv("SITE_MODE", "local")

    instructor_profile = _create_instructor(
        db, email="instructor@example.com", status="pending"
    )

    stub_service = SimpleNamespace(
        instructor_profile_id=instructor_profile.id,
        duration_options=[30],
    )

    class StubConflictRepository:
        def get_active_service(self, _service_id):
            return stub_service

        def get_instructor_profile(self, _instructor_id):
            return instructor_profile

    booking_service = BookingService(
        db,
        conflict_checker_repository=StubConflictRepository(),
    )

    student = SimpleNamespace(
        id="student1",
        roles=[SimpleNamespace(name=RoleName.STUDENT)],
    )

    booking_data = BookingCreate(
        instructor_id=instructor_profile.user_id,
        instructor_service_id="service1",
        booking_date=date.today(),
        start_time=time(9, 0),
        selected_duration=30,
    )

    service, profile = await booking_service._validate_booking_prerequisites(student, booking_data)
    assert service.instructor_profile_id == profile.id
