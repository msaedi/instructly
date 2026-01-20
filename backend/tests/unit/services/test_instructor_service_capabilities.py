from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import BusinessRuleException, ValidationException
from app.models.address import InstructorServiceArea
from app.models.instructor import InstructorPreferredPlace, InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService


def _get_service(db, instructor_id: str) -> Service:
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
    )
    if not profile:
        raise RuntimeError("Instructor profile missing in test fixture")
    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id)
        .order_by(Service.created_at.asc())
        .first()
    )
    if not service:
        raise RuntimeError("Instructor service missing in test fixture")
    return service


class TestServiceCapabilityValidation:
    def test_offers_travel_requires_service_areas(self, db, test_instructor) -> None:
        service = _get_service(db, test_instructor.id)
        db.query(InstructorServiceArea).filter(
            InstructorServiceArea.instructor_id == test_instructor.id
        ).update({"is_active": False})
        db.flush()

        service.offers_travel = True
        service.offers_online = True
        service.offers_at_location = False

        instructor_service = InstructorService(db)
        with pytest.raises(BusinessRuleException) as exc:
            instructor_service.validate_service_capabilities(service, test_instructor.id)

        assert exc.value.code == "NO_SERVICE_AREAS"

    def test_offers_at_location_requires_teaching_locations(self, db, test_instructor) -> None:
        service = _get_service(db, test_instructor.id)
        db.query(InstructorPreferredPlace).filter(
            InstructorPreferredPlace.instructor_id == test_instructor.id
        ).delete()
        db.flush()

        service.offers_at_location = True
        service.offers_online = True
        service.offers_travel = False

        instructor_service = InstructorService(db)
        with pytest.raises(BusinessRuleException) as exc:
            instructor_service.validate_service_capabilities(service, test_instructor.id)

        assert exc.value.code == "NO_TEACHING_LOCATIONS"

    def test_at_least_one_capability_required(self, db, test_instructor) -> None:
        service = _get_service(db, test_instructor.id)
        service.offers_travel = False
        service.offers_at_location = False
        service.offers_online = False

        instructor_service = InstructorService(db)
        with pytest.raises(BusinessRuleException) as exc:
            instructor_service.validate_service_capabilities(service, test_instructor.id)

        assert exc.value.code == "NO_LOCATION_OPTIONS"

    def test_valid_capabilities_with_requirements_met(self, db, test_instructor) -> None:
        service = _get_service(db, test_instructor.id)
        place = InstructorPreferredPlace(
            instructor_id=test_instructor.id,
            kind="teaching_location",
            address="123 Studio Lane, New York, NY",
            label="Studio",
            position=0,
        )
        db.add(place)
        db.flush()

        service.offers_travel = True
        service.offers_at_location = True
        service.offers_online = True

        instructor_service = InstructorService(db)
        instructor_service.validate_service_capabilities(service, test_instructor.id)


class TestBookingCapabilityValidation:
    def test_student_location_requires_offers_travel(self, db) -> None:
        booking_service = BookingService(db)
        service = SimpleNamespace(offers_travel=False, offers_at_location=False, offers_online=True)

        with pytest.raises(ValidationException) as exc:
            booking_service._validate_location_capability(service, "student_location")

        assert exc.value.code == "TRAVEL_NOT_OFFERED"

    def test_instructor_location_requires_offers_at_location(self, db) -> None:
        booking_service = BookingService(db)
        service = SimpleNamespace(offers_travel=True, offers_at_location=False, offers_online=True)

        with pytest.raises(ValidationException) as exc:
            booking_service._validate_location_capability(service, "instructor_location")

        assert exc.value.code == "AT_LOCATION_NOT_OFFERED"

    def test_online_requires_offers_online(self, db) -> None:
        booking_service = BookingService(db)
        service = SimpleNamespace(offers_travel=True, offers_at_location=True, offers_online=False)

        with pytest.raises(ValidationException) as exc:
            booking_service._validate_location_capability(service, "online")

        assert exc.value.code == "ONLINE_NOT_OFFERED"

    def test_neutral_location_requires_offers_travel(self, db) -> None:
        booking_service = BookingService(db)
        service = SimpleNamespace(offers_travel=False, offers_at_location=True, offers_online=True)

        with pytest.raises(ValidationException) as exc:
            booking_service._validate_location_capability(service, "neutral_location")

        assert exc.value.code == "TRAVEL_NOT_OFFERED"
