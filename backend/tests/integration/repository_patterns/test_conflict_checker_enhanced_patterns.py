# backend/tests/integration/repository_patterns/test_conflict_checker_enhanced_patterns.py
"""
Enhanced query patterns for ConflictCheckerRepository.

Documents missing query patterns identified in the analysis:
- get_blackouts_in_range
- get_bookings_in_range
- get_detailed_bookings_for_conflict_check
- get_instructor_booking_summary
- get_time_utilization_stats
"""

from datetime import date, time, timedelta

from sqlalchemy import and_, case, extract, func, text
from sqlalchemy.orm import Session, joinedload

from app.models.availability import BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User


def get_test_service(db: Session, instructor: User) -> Service:
    """Helper function to get the first active service for a test instructor."""
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    if not profile:
        raise ValueError(f"No profile found for instructor {instructor.id}")

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
    if not service:
        raise ValueError(f"No active service found for profile {profile.id}")

    return service


class TestConflictCheckerEnhancedPatterns:
    """Document missing query patterns for ConflictCheckerRepository."""

    def test_query_pattern_get_blackouts_in_range(self, db: Session, test_instructor: User):
        """Document query for getting blackout dates in a date range."""
        instructor_id = test_instructor.id
        start_date = date.today()
        end_date = start_date + timedelta(days=30)

        # Create test blackout dates
        blackout_dates = [
            date.today() + timedelta(days=5),
            date.today() + timedelta(days=15),
            date.today() + timedelta(days=25),
            date.today() + timedelta(days=35),  # Outside range
        ]

        for blackout_date in blackout_dates:
            blackout = BlackoutDate(
                instructor_id=instructor_id, date=blackout_date, reason=f"Unavailable on {blackout_date}"
            )
            db.add(blackout)
        db.commit()

        # Document the query pattern
        query = (
            db.query(BlackoutDate)
            .filter(
                and_(
                    BlackoutDate.instructor_id == instructor_id,
                    BlackoutDate.date >= start_date,
                    BlackoutDate.date <= end_date,
                )
            )
            .order_by(BlackoutDate.date)
        )

        results = query.all()

        # Repository method signature:
        # def get_blackouts_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[BlackoutDate]

        assert len(results) == 3  # Only dates within range
        assert all(start_date <= b.date <= end_date for b in results)
        assert results[0].date == blackout_dates[0]

    def test_query_pattern_get_bookings_in_range(self, db: Session, test_instructor: User, test_student: User):
        """Document query for getting all bookings in a date range."""
        instructor_id = test_instructor.id
        start_date = date.today()
        end_date = start_date + timedelta(days=14)

        # Create bookings across the range
        test_service = get_test_service(db, test_instructor)
        for day_offset in [0, 3, 7, 10, 14, 20]:  # Last one outside range
            booking = Booking(
                instructor_id=instructor_id,
                student_id=test_student.id,
                booking_date=start_date + timedelta(days=day_offset),
                start_time=time(10, 0),
                end_time=time(11, 0),
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
        db.commit()

        # Document the query pattern - include all statuses
        query = (
            db.query(Booking)
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                )
            )
            .order_by(Booking.booking_date, Booking.start_time)
        )

        results = query.all()

        # Repository method signature:
        # def get_bookings_in_range(self, instructor_id: int, start_date: date, end_date: date, include_cancelled: bool = False) -> List[Booking]

        assert len(results) == 5  # Excludes the one outside range
        assert all(start_date <= b.booking_date <= end_date for b in results)

    def test_query_pattern_get_detailed_bookings_for_conflict_check(
        self, db: Session, test_instructor: User, test_student: User
    ):
        """Document query for detailed booking info needed for conflict checking."""
        instructor_id = test_instructor.id
        check_date = date.today() + timedelta(days=7)

        # Create bookings with same student
        test_service = get_test_service(db, test_instructor)
        for i in range(3):
            booking = Booking(
                instructor_id=instructor_id,
                student_id=test_student.id,
                booking_date=check_date,
                start_time=time(9 + i * 2, 0),
                end_time=time(10 + i * 2, 0),
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
        db.commit()

        # Complex query with all details needed for conflict checking
        query = (
            db.query(Booking)
            .options(
                joinedload(Booking.student),
                joinedload(Booking.instructor_service).joinedload(Service.instructor_profile),
            )
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date == check_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
            .order_by(Booking.start_time)
        )

        results = query.all()

        # Repository method signature:
        # def get_detailed_bookings_for_conflict_check(self, instructor_id: int, date: date) -> List[Booking]

        assert len(results) == 3
        # Verify eager loading worked
        for booking in results:
            assert booking.student is not None
            assert booking.instructor_service is not None
            assert hasattr(booking.student, "first_name")
            assert hasattr(booking.student, "last_name")  # No additional query

    def test_query_pattern_get_instructor_booking_summary(self, db: Session, test_instructor: User, test_student: User):
        """Document aggregation query for instructor booking summary."""
        instructor_id = test_instructor.id

        # Create various bookings over past 30 days
        test_service = get_test_service(db, test_instructor)
        today = date.today()
        for i in range(20):
            booking_date = today - timedelta(days=i)
            status = BookingStatus.COMPLETED if i > 5 else BookingStatus.CONFIRMED

            booking = Booking(
                instructor_id=instructor_id,
                student_id=test_student.id,
                booking_date=booking_date,
                start_time=time(10, 0),
                end_time=time(11 + (i % 2), 0),  # Vary duration
                status=status,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60 + (i % 2) * 60,
            )
            db.add(booking)

        # Add some cancelled bookings
        for i in range(5):
            booking = Booking(
                instructor_id=instructor_id,
                student_id=test_student.id,
                booking_date=today - timedelta(days=i),
                start_time=time(14, 0),
                end_time=time(15, 0),
                status=BookingStatus.CANCELLED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)

        db.commit()

        # Complex aggregation query
        query = (
            db.query(
                Booking.instructor_id,
                func.count(Booking.id).label("total_bookings"),
                func.count(case((Booking.status == BookingStatus.COMPLETED, 1))).label("completed_bookings"),
                func.count(case((Booking.status == BookingStatus.CONFIRMED, 1))).label("confirmed_bookings"),
                func.count(case((Booking.status == BookingStatus.CANCELLED, 1))).label("cancelled_bookings"),
                func.count(func.distinct(Booking.student_id)).label("unique_students"),
                func.sum(extract("epoch", text("bookings.end_time::time - bookings.start_time::time")) / 3600).label(
                    "total_hours"
                ),
            )
            .filter(and_(Booking.instructor_id == instructor_id, Booking.booking_date >= today - timedelta(days=30)))
            .group_by(Booking.instructor_id)
        )

        result = query.first()

        # Repository method signature:
        # def get_instructor_booking_summary(self, instructor_id: int, days: int = 30) -> Dict[str, Any]

        assert result is not None
        assert result.total_bookings == 25  # 20 + 5
        assert result.completed_bookings == 14  # Days > 5
        assert result.confirmed_bookings == 6  # Days <= 5
        assert result.cancelled_bookings == 5
        assert result.unique_students >= 1

    def test_query_pattern_get_time_utilization_stats(self, db: Session, test_instructor: User, test_student: User):
        """Document query for time utilization statistics."""
        instructor_id = test_instructor.id
        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        # Create bookings with various time patterns
        test_service = get_test_service(db, test_instructor)
        booking_patterns = [
            # (day_offset, bookings_for_day)
            (0, [(time(9, 0), time(11, 0)), (time(14, 0), time(16, 0))]),  # 4 hours
            (1, [(time(10, 0), time(12, 0))]),  # 2 hours
            (2, [(time(9, 0), time(17, 0))]),  # 8 hours (full day)
            (3, []),  # No bookings
            (4, [(time(13, 0), time(14, 0)), (time(15, 0), time(16, 0))]),  # 2 hours
        ]

        for day_offset, day_bookings in booking_patterns:
            booking_date = start_date + timedelta(days=day_offset)
            for start, end in day_bookings:
                booking = Booking(
                    instructor_id=instructor_id,
                    student_id=test_student.id,
                    booking_date=booking_date,
                    start_time=start,
                    end_time=end,
                    status=BookingStatus.CONFIRMED,
                    instructor_service_id=test_service.id,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                )
                db.add(booking)
        db.commit()

        # Time utilization query
        daily_stats = (
            db.query(
                Booking.booking_date,
                func.count(Booking.id).label("bookings_count"),
                func.sum(extract("epoch", text("bookings.end_time::time - bookings.start_time::time")) / 3600).label(
                    "booked_hours"
                ),
                func.min(Booking.start_time).label("first_booking"),
                func.max(Booking.end_time).label("last_booking"),
            )
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
            .group_by(Booking.booking_date)
            .order_by(Booking.booking_date)
        )

        results = daily_stats.all()

        # Repository method signature:
        # def get_time_utilization_stats(self, instructor_id: int, start_date: date, end_date: date) -> List[Dict[str, Any]]

        assert len(results) == 4  # Days with bookings

        # Verify stats for first day
        first_day = results[0]
        assert first_day.bookings_count == 2
        assert first_day.booked_hours == 4.0
        assert first_day.first_booking == time(9, 0)
        assert first_day.last_booking == time(16, 0)

    def test_query_pattern_check_multi_day_conflicts(self, db: Session, test_instructor: User, test_student: User):
        """Document query for checking conflicts across multiple days."""
        instructor_id = test_instructor.id

        # Create existing bookings
        test_service = get_test_service(db, test_instructor)
        existing_dates = [
            date.today() + timedelta(days=10),
            date.today() + timedelta(days=11),
            date.today() + timedelta(days=12),
        ]

        for booking_date in existing_dates:
            booking = Booking(
                instructor_id=instructor_id,
                student_id=test_student.id,
                booking_date=booking_date,
                start_time=time(10, 0),
                end_time=time(11, 0),
                status=BookingStatus.CONFIRMED,
                instructor_service_id=test_service.id,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
            db.add(booking)
        db.commit()

        # Check for conflicts in the same time slot across multiple days
        check_dates = existing_dates[:2] + [date.today() + timedelta(days=13)]
        check_start = time(10, 0)
        check_end = time(11, 0)

        # Query for conflicts across multiple days
        conflicts = (
            db.query(Booking)
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date.in_(check_dates),
                    Booking.start_time < check_end,
                    Booking.end_time > check_start,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
            .all()
        )

        # Repository method signature:
        # def check_multi_day_conflicts(self, instructor_id: int, dates: List[date],
        #                              start_time: time, end_time: time) -> List[Booking]

        assert len(conflicts) == 2  # Only the first two dates have conflicts

    def test_query_pattern_get_peak_hours_analysis(self, db: Session, test_instructor: User, test_student: User):
        """Document query for analyzing peak booking hours."""
        instructor_id = test_instructor.id

        # Create bookings at various times over 30 days
        test_service = get_test_service(db, test_instructor)
        for day in range(30):
            booking_date = date.today() - timedelta(days=day)

            # Morning bookings (more common)
            if day % 3 != 2:  # 2/3 of days
                booking = Booking(
                    instructor_id=instructor_id,
                    student_id=test_student.id,
                    booking_date=booking_date,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                    status=BookingStatus.COMPLETED,
                    instructor_service_id=test_service.id,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                )
                db.add(booking)

            # Afternoon bookings (less common)
            if day % 2 == 0:  # 1/2 of days
                booking = Booking(
                    instructor_id=instructor_id,
                    student_id=test_student.id,
                    booking_date=booking_date,
                    start_time=time(14, 0),
                    end_time=time(15, 0),
                    status=BookingStatus.COMPLETED,
                    instructor_service_id=test_service.id,
                    service_name="Test Service",
                    hourly_rate=50.0,
                    total_price=50.0,
                    duration_minutes=60,
                )
                db.add(booking)

        db.commit()

        # Peak hours analysis query
        peak_hours = (
            db.query(
                extract("hour", Booking.start_time).label("hour"),
                func.count(Booking.id).label("booking_count"),
                func.count(func.distinct(Booking.booking_date)).label("days_with_bookings"),
            )
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    Booking.booking_date >= date.today() - timedelta(days=30),
                )
            )
            .group_by(extract("hour", Booking.start_time))
            .order_by(func.count(Booking.id).desc())
        )

        results = peak_hours.all()

        # Repository method signature:
        # def get_peak_hours_analysis(self, instructor_id: int, days: int = 30) -> List[Dict[str, Any]]

        assert len(results) >= 2
        # Morning slot should be most popular
        assert results[0].hour == 9
        assert results[0].booking_count >= 20  # ~2/3 of 30 days

    def test_query_pattern_get_conflict_check_with_buffer_time(
        self, db: Session, test_instructor: User, test_student: User
    ):
        """Document query for conflict checking with buffer time consideration."""
        instructor_id = test_instructor.id
        check_date = date.today() + timedelta(days=20)
        buffer_minutes = 15

        # Create a booking
        test_service = get_test_service(db, test_instructor)
        existing_booking = Booking(
            instructor_id=instructor_id,
            student_id=test_student.id,
            booking_date=check_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            status=BookingStatus.CONFIRMED,
            instructor_service_id=test_service.id,
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
        )
        db.add(existing_booking)
        db.commit()

        # Check for conflicts with buffer time
        check_start = time(11, 0)  # Exactly at end
        check_end = time(12, 0)

        # Query that considers buffer time

        # Use raw SQL for the buffer time calculation
        conflicts_with_buffer = db.execute(
            text(
                f"""
                SELECT * FROM bookings
                WHERE instructor_id = :instructor_id
                AND booking_date = :check_date
                AND status IN ('CONFIRMED', 'COMPLETED')
                AND (end_time + INTERVAL '{buffer_minutes} minutes')::time > :check_start
                AND (start_time - INTERVAL '{buffer_minutes} minutes')::time < :check_end
            """
            ),
            {
                "instructor_id": instructor_id,
                "check_date": check_date,
                "check_start": check_start,
                "check_end": check_end,
            },
        ).fetchall()

        # Repository method signature:
        # def check_conflicts_with_buffer(self, instructor_id: int, date: date,
        #                                start_time: time, end_time: time,
        #                                buffer_minutes: int) -> List[Booking]

        # Should find conflict due to buffer time
        assert len(conflicts_with_buffer) == 1

        # Without buffer, no conflict
        conflicts_no_buffer = (
            db.query(Booking)
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date == check_date,
                    Booking.start_time < check_end,
                    Booking.end_time > check_start,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
            .all()
        )

        assert len(conflicts_no_buffer) == 0
