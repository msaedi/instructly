# backend/tests/integration/test_booking_query_patterns.py
"""
Document all query patterns used in BookingService.

This serves as the specification for the BookingRepository
that will be implemented in the repository pattern.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session, joinedload

from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


# Add the missing fixture
@pytest.fixture
def test_service(db: Session, test_instructor: User) -> Service:
    """Create a test service for the instructor."""
    # Get or create instructor profile
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

    if not profile:
        profile = InstructorProfile(
            user_id=test_instructor.id,
            bio="Test instructor bio",
            years_experience=5,
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()

    # Create service
    service = Service(
        instructor_profile_id=profile.id,
        skill="Test Service",
        hourly_rate=50.0,
        description="Test service description",
        is_active=True,
    )
    db.add(service)
    db.commit()

    return service


class TestBookingQueryPatterns:
    """Document every query pattern that needs repository implementation."""

    def test_query_pattern_check_slot_booking(self, db: Session, test_booking: Booking):
        """Document query for checking if a slot has existing booking."""
        slot_id = test_booking.availability_slot_id

        # Document the exact query pattern
        existing_booking = (
            db.query(Booking)
            .filter(
                Booking.availability_slot_id == slot_id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .first()
        )

        # Repository method signature:
        # def get_booking_for_slot(self, slot_id: int, active_only: bool = True) -> Optional[Booking]

        if existing_booking:
            assert hasattr(existing_booking, "status")
            assert existing_booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

    def test_query_pattern_get_bookings_filtered(self, db: Session, test_student: User, test_instructor: User):
        """Document query for getting bookings with filters and eager loading."""
        # Basic query with eager loading
        query = db.query(Booking).options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service),
            joinedload(Booking.availability_slot),
        )

        # Filter by student
        student_bookings = query.filter(Booking.student_id == test_student.id).all()

        # Filter by instructor
        instructor_bookings = query.filter(Booking.instructor_id == test_instructor.id).all()

        # Filter by status
        confirmed_bookings = query.filter(Booking.status == BookingStatus.CONFIRMED).all()

        # Filter by date range
        today = date.today()
        week_later = today + timedelta(days=7)
        date_range_bookings = query.filter(Booking.booking_date >= today, Booking.booking_date <= week_later).all()

        # Repository method signatures:
        # def get_bookings(self, user_id: int = None, user_role: str = None,
        #                  status: BookingStatus = None, date_start: date = None,
        #                  date_end: date = None, skip: int = 0, limit: int = 100) -> List[Booking]
        # def get_student_bookings(self, student_id: int, status: BookingStatus = None) -> List[Booking]
        # def get_instructor_bookings(self, instructor_id: int, status: BookingStatus = None) -> List[Booking]

        for booking in student_bookings:
            assert booking.student_id == test_student.id

    def test_query_pattern_get_booking_by_id(self, db: Session, test_booking: Booking):
        """Document query for getting a single booking with all relationships."""
        booking_id = test_booking.id

        # Document the exact query pattern
        booking = (
            db.query(Booking)
            .options(
                joinedload(Booking.student),
                joinedload(Booking.instructor),
                joinedload(Booking.service).joinedload(Service.instructor_profile),
                joinedload(Booking.availability_slot).joinedload(AvailabilitySlot.availability),
                joinedload(Booking.cancelled_by),
            )
            .filter(Booking.id == booking_id)
            .first()
        )

        # Repository method signature:
        # def get_booking_with_details(self, booking_id: int) -> Optional[Booking]

        assert booking is not None
        assert booking.id == booking_id
        # Verify relationships are loaded
        assert booking.student is not None
        assert booking.instructor is not None

    def test_query_pattern_get_instructor_stats(self, db: Session, test_instructor_with_bookings: User):
        """Document query for getting all bookings for statistics."""
        instructor_id = test_instructor_with_bookings.id

        # Document the exact query pattern
        bookings = db.query(Booking).filter(Booking.instructor_id == instructor_id).all()

        # Repository method signature:
        # def get_instructor_bookings_for_stats(self, instructor_id: int) -> List[Booking]

        assert len(bookings) > 0
        for booking in bookings:
            assert booking.instructor_id == instructor_id

    def test_query_pattern_get_availability_slot(self, db: Session, test_booking: Booking):
        """Document query for loading availability slot with relationships."""
        slot_id = test_booking.availability_slot_id

        # Document the exact query pattern
        slot = (
            db.query(AvailabilitySlot)
            .options(joinedload(AvailabilitySlot.availability))
            .filter(AvailabilitySlot.id == slot_id)
            .first()
        )

        # Repository method signature:
        # def get_availability_slot_with_details(self, slot_id: int) -> Optional[AvailabilitySlot]

        assert slot is not None
        assert slot.id == slot_id
        assert slot.availability is not None

    def test_query_pattern_get_active_service(self, db: Session, test_service: Service):
        """Document query for loading active service with instructor profile."""
        service_id = test_service.id

        # Document the exact query pattern
        service = (
            db.query(Service)
            .options(joinedload(Service.instructor_profile))
            .filter(Service.id == service_id, Service.is_active == True)
            .first()
        )

        # Repository method signature:
        # def get_active_service_with_profile(self, service_id: int) -> Optional[Service]

        if service:
            assert service.is_active is True
            assert service.instructor_profile is not None

    def test_query_pattern_get_bookings_for_reminders(self, db: Session):
        """Document query for getting bookings that need reminders."""
        tomorrow = date.today() + timedelta(days=1)

        # Document the exact query pattern
        bookings = (
            db.query(Booking)
            .filter(
                Booking.booking_date == tomorrow,
                Booking.status == BookingStatus.CONFIRMED,
            )
            .options(joinedload(Booking.student), joinedload(Booking.instructor))
            .all()
        )

        # Repository method signature:
        # def get_bookings_for_date(self, booking_date: date, status: BookingStatus = None,
        #                          with_relationships: bool = False) -> List[Booking]

        for booking in bookings:
            assert booking.booking_date == tomorrow
            assert booking.status == BookingStatus.CONFIRMED

    def test_query_pattern_upcoming_bookings(self, db: Session, test_student: User):
        """Document query for getting upcoming bookings with ordering."""
        # Query with date filter and ordering
        query = (
            db.query(Booking)
            .options(
                joinedload(Booking.instructor),
                joinedload(Booking.service),
                joinedload(Booking.availability_slot),
            )
            .filter(
                Booking.student_id == test_student.id,
                Booking.booking_date >= date.today(),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(Booking.booking_date, Booking.start_time)
        )

        bookings = query.all()

        # Repository method signature:
        # def get_upcoming_bookings(self, user_id: int, user_role: str) -> List[Booking]

        # Verify ordering
        for i in range(1, len(bookings)):
            assert bookings[i - 1].booking_date <= bookings[i].booking_date

    def test_query_pattern_count_operations(self, db: Session, test_instructor_with_bookings: User):
        """Document count queries used in the service."""
        instructor_id = test_instructor_with_bookings.id

        # Count total bookings
        total_count = db.query(Booking).filter(Booking.instructor_id == instructor_id).count()

        # Count by status
        confirmed_count = (
            db.query(Booking)
            .filter(Booking.instructor_id == instructor_id, Booking.status == BookingStatus.CONFIRMED)
            .count()
        )

        completed_count = (
            db.query(Booking)
            .filter(Booking.instructor_id == instructor_id, Booking.status == BookingStatus.COMPLETED)
            .count()
        )

        # Repository method signatures:
        # def count_bookings(self, instructor_id: int = None, student_id: int = None,
        #                   status: BookingStatus = None) -> int
        # def count_bookings_by_status(self, user_id: int, user_role: str) -> Dict[str, int]

        assert total_count >= 0
        assert confirmed_count >= 0
        assert completed_count >= 0
        assert total_count >= confirmed_count + completed_count

    def test_query_pattern_bulk_operations(self, db: Session):
        """Document patterns for bulk operations if any."""
        # BookingService doesn't seem to have bulk operations
        # But we should support bulk create for future features

        # Repository method signature (future):
        # def bulk_create_bookings(self, bookings: List[Dict]) -> List[Booking]

    def test_query_pattern_check_conflicts(self, db: Session, test_instructor: User):
        """Document query for checking booking conflicts."""
        booking_date = date.today() + timedelta(days=7)
        start_time = time(14, 0)
        end_time = time(15, 0)

        # Check for overlapping bookings
        conflicts = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                # Time overlap check
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )
            .all()
        )

        # Repository method signature:
        # def check_booking_conflicts(self, instructor_id: int, booking_date: date,
        #                           start_time: time, end_time: time,
        #                           exclude_booking_id: int = None) -> List[Booking]

        # All returned bookings should be conflicts
        for booking in conflicts:
            assert booking.instructor_id == test_instructor.id
            assert booking.booking_date == booking_date
            assert booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

    def test_query_pattern_transaction_support(self, db: Session):
        """Document that repository should support transactions."""
        # BookingService uses transactions for create_booking
        # Repository should use flush() not commit()

        # The service will manage transactions:
        # with self.transaction():
        #     booking = repository.create_booking(...)
        #     repository.flush()  # Get ID without committing
        #     # ... other operations ...
        #     self.db.commit()

        # Repository methods should support being called within transactions

    def test_query_pattern_pagination_support(self, db: Session, test_student: User):
        """Document pagination pattern for list queries."""
        skip = 0
        limit = 10

        # Query with pagination
        bookings = (
            db.query(Booking)
            .filter(Booking.student_id == test_student.id)
            .order_by(Booking.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        # Repository should support skip/limit parameters
        # Already included in get_bookings method signature

        assert len(bookings) <= limit

    def test_query_pattern_summary(self):
        """
        Summary of all BookingRepository methods needed based on query patterns:

        BOOKING-SPECIFIC METHODS:
        1. get_booking_for_slot(slot_id: int, active_only: bool = True) -> Optional[Booking]
        2. get_bookings(user_id: int = None, user_role: str = None, status: BookingStatus = None,
                       date_start: date = None, date_end: date = None, skip: int = 0, limit: int = 100) -> List[Booking]
        3. get_student_bookings(student_id: int, status: BookingStatus = None,
                               upcoming_only: bool = False, limit: int = None) -> List[Booking]
        4. get_instructor_bookings(instructor_id: int, status: BookingStatus = None,
                                  upcoming_only: bool = False, limit: int = None) -> List[Booking]
        5. get_booking_with_details(booking_id: int) -> Optional[Booking]
        6. get_instructor_bookings_for_stats(instructor_id: int) -> List[Booking]
        7. get_bookings_for_date(booking_date: date, status: BookingStatus = None,
                               with_relationships: bool = False) -> List[Booking]
        8. get_upcoming_bookings(user_id: int, user_role: str) -> List[Booking]
        9. count_bookings(instructor_id: int = None, student_id: int = None,
                         status: BookingStatus = None) -> int
        10. count_bookings_by_status(user_id: int, user_role: str) -> Dict[str, int]
        11. check_booking_conflicts(instructor_id: int, booking_date: date, start_time: time,
                                   end_time: time, exclude_booking_id: int = None) -> List[Booking]

        METHODS THAT BELONG IN OTHER REPOSITORIES:
        - get_availability_slot_with_details() -> Should be in AvailabilityRepository
        - get_active_service_with_profile() -> Should be in SlotManagerRepository or ServiceRepository

        Plus standard CRUD operations from BaseRepository:
        - create(booking_data) with transaction support
        - update(booking_id, update_data)
        - Standard find/count/exists methods
        """
