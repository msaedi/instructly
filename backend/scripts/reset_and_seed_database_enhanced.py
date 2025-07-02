#!/usr/bin/env python3
# backend/scripts/reset_and_seed_database_enhanced.py
"""
Enhanced Database reset and seed script with soft delete testing.

UPDATED for Work Stream #9: Bookings no longer reference availability_slot_id.
Bookings are created as independent commitments with just time/date/instructor info.

Features:
- Creates past bookings with services that will be soft deleted
- Generates availability and bookings in past 2 weeks and future 3 weeks
- Tests copy from previous week functionality
- Creates realistic workload patterns
- Bookings exist independently of availability slots
"""

import logging
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability  # noqa: E402
from app.models.booking import Booking, BookingStatus  # noqa: E402
from app.models.instructor import InstructorProfile  # noqa: E402
from app.models.password_reset import PasswordResetToken  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

# Enhanced logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
EXCLUDE_FROM_CLEANUP = [
    "mehdisaedi@hotmail.com",
    "mehdi@saedi.ca",
]

TEST_PASSWORD = "TestPassword123!"

# NYC areas
NYC_AREAS = [
    "Manhattan - Upper East Side",
    "Manhattan - Upper West Side",
    "Manhattan - Midtown",
    "Manhattan - Chelsea",
    "Manhattan - Greenwich Village",
    "Brooklyn - Park Slope",
    "Queens - Astoria",
]

# Instructor templates with services that will be soft deleted
INSTRUCTOR_TEMPLATES = [
    {
        "name": "Sarah Chen",
        "email": "sarah.chen@example.com",
        "bio": "Experienced piano and music theory instructor with 15 years of teaching experience. Specializes in classical and jazz piano for all skill levels.",
        "years_experience": 15,
        "areas": ["Manhattan - Upper East Side", "Manhattan - Upper West Side", "Manhattan - Midtown"],
        "services": [
            {"skill": "Piano", "rate": 80, "desc": "Classical and jazz piano for all levels"},
            {"skill": "Music Theory", "rate": 70, "desc": "Comprehensive music theory and composition"},
        ],
        # Service that will be soft deleted after creating past bookings
        "deprecated_service": {"skill": "Sight Reading", "rate": 60, "desc": "Sight reading practice sessions"},
    },
    {
        "name": "Michael Rodriguez",
        "email": "michael.rodriguez@example.com",
        "bio": "Professional guitarist and guitar instructor. Expert in rock, blues, and acoustic styles. Patient approach perfect for beginners.",
        "years_experience": 10,
        "areas": ["Brooklyn - Park Slope", "Brooklyn - DUMBO", "Manhattan - Greenwich Village"],
        "services": [
            {"skill": "Guitar", "rate": 75, "desc": "Electric and acoustic guitar lessons"},
            {"skill": "Bass Guitar", "rate": 75, "desc": "Bass guitar fundamentals and advanced techniques"},
        ],
        # Service that will be soft deleted
        "deprecated_service": {"skill": "Ukulele", "rate": 50, "desc": "Beginner ukulele lessons"},
    },
    {
        "name": "Emily Watson",
        "email": "emily.watson@example.com",
        "bio": "Certified math tutor specializing in high school and college-level mathematics. SAT/ACT prep expert with proven results.",
        "years_experience": 8,
        "areas": ["Manhattan - Chelsea", "Manhattan - Greenwich Village", "Manhattan - SoHo"],
        "services": [
            {"skill": "Math Tutoring", "rate": 90, "desc": "Algebra, Calculus, and Statistics"},
            {"skill": "SAT/ACT Prep", "rate": 100, "desc": "Comprehensive test preparation"},
        ],
        "deprecated_service": None,  # Not all instructors need deprecated services
    },
    {
        "name": "James Kim",
        "email": "james.kim@example.com",
        "bio": "Professional software engineer offering programming lessons. Specializes in Python, JavaScript, and web development.",
        "years_experience": 12,
        "areas": ["Queens - Long Island City", "Queens - Astoria", "Manhattan - Midtown"],
        "services": [
            {"skill": "Python Programming", "rate": 95, "desc": "From basics to advanced Python development"},
            {"skill": "Web Development", "rate": 100, "desc": "HTML, CSS, JavaScript, and React"},
        ],
        "deprecated_service": {"skill": "Java Programming", "rate": 90, "desc": "Java fundamentals and OOP"},
    },
]

STUDENT_TEMPLATES = [
    {"name": "John Smith", "email": "john.smith@example.com"},
    {"name": "Emma Johnson", "email": "emma.johnson@example.com"},
    {"name": "William Brown", "email": "william.brown@example.com"},
    {"name": "Sophia Davis", "email": "sophia.davis@example.com"},
    {"name": "Oliver Wilson", "email": "oliver.wilson@example.com"},
    {"name": "Isabella Martinez", "email": "isabella.martinez@example.com"},
    {"name": "Lucas Anderson", "email": "lucas.anderson@example.com"},
    {"name": "Mia Thompson", "email": "mia.thompson@example.com"},
]


def cleanup_database(session: Session) -> List[int]:
    """Enhanced cleanup with proper dependency handling."""
    logger.info("Starting database cleanup...")
    start_time = datetime.now()

    # Get users to exclude
    excluded_users = session.query(User).filter(User.email.in_(EXCLUDE_FROM_CLEANUP)).all()
    excluded_ids = [user.id for user in excluded_users]
    logger.info(f"Preserving {len(excluded_ids)} users")

    # Get all test users to delete
    users_to_delete = (
        session.query(User)
        .filter(
            ~User.id.in_(excluded_ids),
            User.email.like("%@example.com"),
        )
        .all()
    )

    user_ids_to_delete = [u.id for u in users_to_delete]
    logger.info(f"Deleting {len(user_ids_to_delete)} users")

    if user_ids_to_delete:
        # Delete in correct order to respect foreign keys

        # 1. Delete bookings
        session.query(Booking).filter(
            or_(
                Booking.student_id.in_(user_ids_to_delete),
                Booking.instructor_id.in_(user_ids_to_delete),
            )
        ).delete(synchronize_session=False)

        # 2. Delete availability slots
        subquery = (
            session.query(InstructorAvailability.id)
            .filter(InstructorAvailability.instructor_id.in_(user_ids_to_delete))
            .subquery()
        )
        session.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id.in_(subquery)).delete(
            synchronize_session=False
        )

        # 3. Delete availability
        session.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id.in_(user_ids_to_delete)
        ).delete(synchronize_session=False)

        # 4. Delete blackout dates
        session.query(BlackoutDate).filter(BlackoutDate.instructor_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 5. Delete services
        profile_subquery = (
            session.query(InstructorProfile.id).filter(InstructorProfile.user_id.in_(user_ids_to_delete)).subquery()
        )
        session.query(Service).filter(Service.instructor_profile_id.in_(profile_subquery)).delete(
            synchronize_session=False
        )

        # 6. Delete instructor profiles
        session.query(InstructorProfile).filter(InstructorProfile.user_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 7. Delete password reset tokens
        session.query(PasswordResetToken).filter(PasswordResetToken.user_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 8. Finally delete users
        session.query(User).filter(User.id.in_(user_ids_to_delete)).delete(synchronize_session=False)

        session.commit()

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Cleanup complete in {duration:.2f}s")

    return excluded_ids


def create_dummy_instructors(session: Session):
    """Create dummy instructors with realistic availability including past weeks."""
    logger.info("Creating dummy instructors...")

    for template in INSTRUCTOR_TEMPLATES:
        # Create user
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=UserRole.INSTRUCTOR,  # Now using VARCHAR, this will just be the string value
            is_active=True,
        )
        session.add(user)
        session.flush()

        # Create profile
        profile = InstructorProfile(
            user_id=user.id,
            bio=template["bio"],
            years_experience=template["years_experience"],
            areas_of_service=", ".join(template["areas"]),
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        session.add(profile)
        session.flush()

        # Create services (including deprecated one if exists)
        services_created = []

        # Add regular services
        for svc in template["services"]:
            service = Service(
                instructor_profile_id=profile.id,
                skill=svc["skill"],
                hourly_rate=svc["rate"],
                description=svc["desc"],
                is_active=True,  # Active services
            )
            session.add(service)
            session.flush()
            services_created.append(service)

        # Add deprecated service if exists
        deprecated_service = None
        if template.get("deprecated_service"):
            svc = template["deprecated_service"]
            deprecated_service = Service(
                instructor_profile_id=profile.id,
                skill=svc["skill"],
                hourly_rate=svc["rate"],
                description=svc["desc"],
                is_active=True,  # Start as active, will be soft deleted later
            )
            session.add(deprecated_service)
            session.flush()

        # Create availability from 2 weeks ago to 3 weeks in future
        create_realistic_availability_with_past(session, user.id)

        # Store for later processing
        template["_user_id"] = user.id
        template["_deprecated_service_id"] = deprecated_service.id if deprecated_service else None
        template["_services"] = services_created

    session.commit()
    logger.info(f"Created {len(INSTRUCTOR_TEMPLATES)} instructors")


def create_realistic_availability_with_past(session: Session, instructor_id: int):
    """Create availability including past 2 weeks and future 3 weeks."""
    today = date.today()
    start_date = today - timedelta(weeks=2)  # 2 weeks ago
    end_date = today + timedelta(weeks=3)  # 3 weeks in future

    # Different patterns for different instructors
    patterns = [
        # Morning person - 9am to 12pm
        [(9, 12)],
        # Afternoon person - 1pm to 5pm
        [(13, 17)],
        # Evening person - 5pm to 9pm
        [(17, 21)],
        # Split schedule - morning and evening
        [(9, 12), (16, 19)],
        # Full day with breaks
        [(9, 12), (13, 17), (18, 20)],
    ]

    pattern = random.choice(patterns)

    # Create consistent weekly pattern
    current_date = start_date
    while current_date <= end_date:
        # Skip some days randomly (20% chance)
        if random.random() < 0.2:
            current_date += timedelta(days=1)
            continue

        # Skip Sundays for some instructors
        if current_date.weekday() == 6 and random.random() < 0.5:
            current_date += timedelta(days=1)
            continue

        # Create availability entry
        availability = InstructorAvailability(instructor_id=instructor_id, date=current_date, is_cleared=False)
        session.add(availability)
        session.flush()

        # Add time slots based on pattern
        for start_hour, end_hour in pattern:
            # Occasionally adjust times slightly for variety
            if random.random() < 0.3:
                start_hour += random.choice([-1, 0, 1])
                end_hour += random.choice([-1, 0, 1])

            # Ensure valid times
            start_hour = max(8, min(20, start_hour))
            end_hour = max(start_hour + 1, min(21, end_hour))

            slot = AvailabilitySlot(
                availability_id=availability.id,
                start_time=time(start_hour, 0),
                end_time=time(end_hour, 0),
            )
            session.add(slot)

        current_date += timedelta(days=1)


def create_dummy_students(session: Session):
    """Create dummy student accounts."""
    logger.info("Creating dummy students...")

    for template in STUDENT_TEMPLATES:
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=UserRole.STUDENT,  # Now using VARCHAR, this will just be the string value
            is_active=True,
        )
        session.add(user)

    session.commit()
    logger.info(f"Created {len(STUDENT_TEMPLATES)} students")


def create_sample_bookings_with_deprecated(session: Session):
    """
    Create bookings including past bookings with services that will be soft deleted.

    UPDATED: Bookings are created independently without referencing availability_slot_id.
    This implements the architectural principle that bookings are independent commitments.
    """
    logger.info("Creating sample bookings (independent of availability slots)...")

    students = session.query(User).filter(User.role == UserRole.STUDENT).all()
    today = date.today()
    bookings_created = 0
    deprecated_bookings_created = 0

    for template in INSTRUCTOR_TEMPLATES:
        if "_user_id" not in template:
            continue

        instructor_id = template["_user_id"]
        deprecated_service_id = template.get("_deprecated_service_id")

        # Get all services for this instructor
        services = (
            session.query(Service).join(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).all()
        )

        if not services:
            continue

        # Get instructor's typical schedule pattern (just for realistic booking times)
        instructor_availabilities = (
            session.query(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date >= today - timedelta(weeks=2),
                InstructorAvailability.date <= today + timedelta(weeks=3),
            )
            .all()
        )

        # Extract typical time patterns from availability
        typical_times = []
        for avail in instructor_availabilities[:5]:  # Sample a few days
            for slot in avail.time_slots:
                typical_times.append((slot.start_time, slot.end_time))

        if not typical_times:
            # Default times if no availability found
            typical_times = [(time(9, 0), time(10, 0)), (time(14, 0), time(15, 0))]

        # Create past bookings with deprecated service
        if deprecated_service_id:
            deprecated_service = session.query(Service).filter(Service.id == deprecated_service_id).first()

            # Create 5 past bookings with deprecated service
            for i in range(5):
                # Random date in the past 2 weeks
                booking_date = today - timedelta(days=random.randint(7, 14))

                # Skip weekends sometimes
                if booking_date.weekday() >= 5 and random.random() < 0.7:
                    continue

                student = random.choice(students)
                start_time, end_time = random.choice(typical_times)

                # Calculate duration
                start_datetime = datetime.combine(date.today(), start_time)
                end_datetime = datetime.combine(date.today(), end_time)
                duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)

                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor_id,
                    service_id=deprecated_service_id,
                    availability_slot_id=None,  # UPDATED: No longer set
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    service_name=deprecated_service.skill,
                    hourly_rate=deprecated_service.hourly_rate,
                    total_price=Decimal(str(deprecated_service.hourly_rate * duration_minutes / 60)),
                    duration_minutes=duration_minutes,
                    status=BookingStatus.COMPLETED,  # Past bookings are completed
                    location_type=random.choice(["student_home", "instructor_location", "neutral"]),
                    meeting_location=f"{random.choice(['Student home', 'Instructor studio', 'Local library'])}",
                    created_at=booking_date - timedelta(days=2),
                    confirmed_at=booking_date - timedelta(days=2),
                    completed_at=booking_date + timedelta(hours=duration_minutes / 60),
                )
                session.add(booking)
                deprecated_bookings_created += 1

        # Create regular bookings (past and future)
        # Generate dates from 2 weeks ago to 3 weeks future
        all_dates = []
        current = today - timedelta(weeks=2)
        while current <= today + timedelta(weeks=3):
            # Skip weekends sometimes
            if current.weekday() < 5 or random.random() < 0.3:
                all_dates.append(current)
            current += timedelta(days=1)

        # Book 30-50% of the dates
        dates_to_book = random.sample(all_dates, min(len(all_dates), int(len(all_dates) * random.uniform(0.3, 0.5))))

        for booking_date in dates_to_book:
            student = random.choice(students)

            # Use only active services for regular bookings
            active_services = [s for s in services if s.is_active and s.id != deprecated_service_id]
            if not active_services:
                continue

            service = random.choice(active_services)

            # Choose random time from typical patterns
            if typical_times:
                start_time, end_time = random.choice(typical_times)
            else:
                # Generate random time if no pattern
                start_hour = random.randint(9, 18)
                start_time = time(start_hour, 0)
                end_time = time(start_hour + random.randint(1, 2), 0)

            # Calculate duration
            start_datetime = datetime.combine(date.today(), start_time)
            end_datetime = datetime.combine(date.today(), end_time)
            duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)

            # Determine booking status based on date
            if booking_date < today:
                status = BookingStatus.COMPLETED
            elif booking_date == today:
                status = BookingStatus.CONFIRMED
            else:
                status = BookingStatus.CONFIRMED

            booking = Booking(
                student_id=student.id,
                instructor_id=instructor_id,
                service_id=service.id,
                availability_slot_id=None,  # UPDATED: No longer set
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                service_name=service.skill,
                hourly_rate=service.hourly_rate,
                total_price=Decimal(str(service.hourly_rate * duration_minutes / 60)),
                duration_minutes=duration_minutes,
                status=status,
                location_type=random.choice(["student_home", "instructor_location", "neutral"]),
                meeting_location=f"{random.choice(['Student home', 'Instructor studio', 'Local library'])}",
                created_at=datetime.now() - timedelta(days=random.randint(1, 14)),
                confirmed_at=datetime.now() - timedelta(days=random.randint(1, 14)),
                completed_at=datetime.now() if status == BookingStatus.COMPLETED else None,
            )
            session.add(booking)
            bookings_created += 1

    session.commit()
    logger.info(f"Created {bookings_created} regular bookings")
    logger.info(f"Created {deprecated_bookings_created} bookings with services to be soft deleted")
    logger.info("Note: Bookings are now independent of availability slots (Work Stream #9)")


def soft_delete_deprecated_services(session: Session):
    """Soft delete the deprecated services that have bookings."""
    logger.info("Soft deleting deprecated services...")

    soft_deleted_count = 0

    for template in INSTRUCTOR_TEMPLATES:
        if "_deprecated_service_id" in template and template["_deprecated_service_id"]:
            service = session.query(Service).filter(Service.id == template["_deprecated_service_id"]).first()

            if service and service.is_active:
                # Check if service has bookings
                has_bookings = session.query(Booking).filter(Booking.service_id == service.id).first() is not None

                if has_bookings:
                    service.is_active = False
                    soft_deleted_count += 1
                    logger.info(f"Soft deleted service: {service.skill} (ID: {service.id})")

    session.commit()
    logger.info(f"Soft deleted {soft_deleted_count} services")


def test_layer_independence(session: Session):
    """Test that bookings persist when availability is deleted."""
    logger.info("\nTesting availability-booking layer independence...")

    # Find a booking from the past week
    past_booking = (
        session.query(Booking)
        .filter(Booking.booking_date < date.today(), Booking.booking_date >= date.today() - timedelta(days=7))
        .first()
    )

    if past_booking:
        # Find availability slots for that instructor on that date
        slots = (
            session.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == past_booking.instructor_id,
                InstructorAvailability.date == past_booking.booking_date,
            )
            .all()
        )

        if slots:
            logger.info(
                f"Found {len(slots)} availability slots for instructor {past_booking.instructor_id} on {past_booking.booking_date}"
            )
            logger.info(f"Deleting these slots to test independence...")

            for slot in slots:
                session.delete(slot)

            session.commit()

            # Verify booking still exists
            booking_check = session.query(Booking).filter(Booking.id == past_booking.id).first()
            if booking_check:
                logger.info("✅ SUCCESS: Booking persists after availability deletion!")
                logger.info(f"   Booking {booking_check.id} still exists for {booking_check.service_name}")
            else:
                logger.error("❌ FAILURE: Booking was deleted with availability!")
        else:
            logger.info("No availability slots found to test deletion")
    else:
        logger.info("No past bookings found to test with")


def main():
    """Main function."""
    logger.info("Starting enhanced database reset and seed process...")
    logger.info("UPDATED: Implementing Work Stream #9 - Bookings independent of availability slots")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session = Session(engine)

    try:
        # Step 1: Cleanup
        cleanup_database(session)

        # Step 2: Create users
        create_dummy_instructors(session)
        create_dummy_students(session)

        # Step 3: Create bookings (now independent of availability slots)
        create_sample_bookings_with_deprecated(session)

        # Step 4: Soft delete deprecated services
        soft_delete_deprecated_services(session)

        # Step 5: Test layer independence
        test_layer_independence(session)

        # Step 6: Summary
        total_users = session.query(User).count()
        total_instructors = session.query(User).filter(User.role == UserRole.INSTRUCTOR).count()
        total_students = session.query(User).filter(User.role == UserRole.STUDENT).count()
        total_bookings = session.query(Booking).count()
        total_services = session.query(Service).count()
        active_services = session.query(Service).filter(Service.is_active == True).count()
        inactive_services = session.query(Service).filter(Service.is_active == False).count()

        # Count bookings by time period
        today = date.today()
        past_bookings = session.query(Booking).filter(Booking.booking_date < today).count()
        future_bookings = session.query(Booking).filter(Booking.booking_date >= today).count()

        # Count bookings with inactive services
        bookings_with_inactive = session.query(Booking).join(Service).filter(Service.is_active == False).count()

        logger.info("\n" + "=" * 50)
        logger.info("Enhanced database reset complete!")
        logger.info(f"Total users: {total_users}")
        logger.info(f"  - Instructors: {total_instructors}")
        logger.info(f"  - Students: {total_students}")
        logger.info(f"\nTotal services: {total_services}")
        logger.info(f"  - Active: {active_services}")
        logger.info(f"  - Inactive (soft deleted): {inactive_services}")
        logger.info(f"\nTotal bookings: {total_bookings}")
        logger.info(f"  - Past bookings: {past_bookings}")
        logger.info(f"  - Future bookings: {future_bookings}")
        logger.info(f"  - Bookings with inactive services: {bookings_with_inactive}")

        logger.info("\nTest credentials:")
        logger.info(f"  All passwords: {TEST_PASSWORD}")
        logger.info("\nInstructors:")
        for t in INSTRUCTOR_TEMPLATES:
            logger.info(f"  - {t['email']}")
        logger.info("\nStudents:")
        for t in STUDENT_TEMPLATES[:3]:
            logger.info(f"  - {t['email']}")

        logger.info("\nSoft delete test:")
        logger.info("  - Sarah Chen: 'Sight Reading' service soft deleted")
        logger.info("  - Michael Rodriguez: 'Ukulele' service soft deleted")
        logger.info("  - James Kim: 'Java Programming' service soft deleted")

        logger.info("\n🎯 ARCHITECTURAL CHANGE (Work Stream #9):")
        logger.info("  - Bookings no longer reference availability_slot_id")
        logger.info("  - Bookings are independent commitments")
        logger.info("  - Availability can be modified without affecting bookings")

    except Exception as e:
        logger.error(f"Error during database reset: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
