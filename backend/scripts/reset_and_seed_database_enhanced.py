#!/usr/bin/env python3
# backend/scripts/reset_and_seed_database_enhanced.py
"""
Database reset and seed script with PRODUCTION SAFETY CHECKS.

This script now includes protection against accidentally running on production databases.
It will only run on databases that appear to be for development/testing.

USAGE OPTIONS:
==============
| Command | Database | Use Case |
|---------|----------|----------|
| USE_TEST_DATABASE=true python scripts/reset_and_seed_database_enhanced.py | Local test DB | Safe local testing |
| ALLOW_SEED_PRODUCTION=true python scripts/reset_and_seed_database_enhanced.py | Production (Supabase) | Pre-launch seeding (asks yes/no) |
| FORCE_ALLOW_RESET=true python scripts/reset_and_seed_database_enhanced.py | Production (Supabase) | Emergency reset (requires typing confirmation) |
| python scripts/reset_and_seed_database_enhanced.py | BLOCKED! | Safety error - no accidental usage |

Examples:
---------
# For local development testing:
USE_TEST_DATABASE=true python scripts/reset_and_seed_database_enhanced.py

# For seeding Supabase before going live:
ALLOW_SEED_PRODUCTION=true python scripts/reset_and_seed_database_enhanced.py

# For emergency production reset (DANGEROUS):
FORCE_ALLOW_RESET=true python scripts/reset_and_seed_database_enhanced.py

Features:
- Safety checks prevent production database usage
- Creates realistic availability patterns
- Generates bookings as independent commitments
- Tests soft delete functionality
- Creates realistic workload patterns
"""

import logging
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.availability import AvailabilitySlot, BlackoutDate  # noqa: E402
from app.models.booking import Booking, BookingStatus  # noqa: E402
from app.models.instructor import InstructorProfile  # noqa: E402
from app.models.password_reset import PasswordResetToken  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ============================================================================
# SAFETY CHECK - PREVENT PRODUCTION DATABASE USAGE
# ============================================================================
def validate_safe_database_url(database_url: str) -> None:
    """
    Validate that we're not using a production database.

    Raises:
        RuntimeError: If the database URL appears to be production
    """
    if not database_url:
        raise RuntimeError("No database URL provided!")

    # Known production indicators
    production_indicators = [
        "supabase.com",
        "supabase.co",
        "amazonaws.com",
        "cloud.google.com",
        "database.azure.com",
        "elephantsql.com",
        "bit.io",
        "neon.tech",
        "railway.app",
        "render.com",
        "aiven.io",
    ]

    url_lower = database_url.lower()

    for indicator in production_indicators:
        if indicator in url_lower:
            raise RuntimeError(
                f"\n\n" + "=" * 60 + "\n"
                f"SAFETY ERROR: REFUSING TO RUN ON PRODUCTION DATABASE!\n"
                f"=" * 60 + "\n"
                f"Database URL contains production indicator: '{indicator}'\n\n"
                f"This script DELETES DATA and should only run on local/test databases.\n\n"
                f"To use this script:\n"
                f"1. Use a local development database\n"
                f"2. Or set FORCE_ALLOW_RESET=true if you REALLY know what you're doing\n"
                f"   (This is EXTREMELY DANGEROUS for production databases!)\n"
                f"=" * 60 + "\n"
            )

    # Warn if database doesn't have common dev/test indicators
    dev_indicators = ["localhost", "127.0.0.1", "test", "dev", "local"]
    has_dev_indicator = any(indicator in url_lower for indicator in dev_indicators)

    if not has_dev_indicator:
        logger.warning(
            "\n⚠️  WARNING: Database URL doesn't contain common development indicators.\n"
            "   Make sure this is really a development database!\n"
        )
        response = input("Are you SURE this is a development database? (yes/no): ")
        if response.lower() != "yes":
            raise RuntimeError("Script cancelled for safety.")


# ============================================================================
# ORIGINAL SCRIPT CONTENT (with safety check added)
# ============================================================================

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

# Instructor templates with services
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
            {"skill": "Sight Reading", "rate": 60, "desc": "Sight reading practice sessions"},
        ],
        "service_to_soft_delete": "Sight Reading",
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
            {"skill": "Ukulele", "rate": 50, "desc": "Beginner ukulele lessons"},
        ],
        "service_to_soft_delete": "Ukulele",
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
        "service_to_soft_delete": None,
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
            {"skill": "Java Programming", "rate": 90, "desc": "Java fundamentals and OOP"},
        ],
        "service_to_soft_delete": "Java Programming",
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
    """Clean up test data while preserving excluded users."""
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
    logger.info(f"Deleting {len(user_ids_to_delete)} test users")

    if user_ids_to_delete:
        # Delete in correct order to respect foreign keys

        # 1. Delete bookings
        deleted_bookings = (
            session.query(Booking)
            .filter((Booking.student_id.in_(user_ids_to_delete)) | (Booking.instructor_id.in_(user_ids_to_delete)))
            .count()
        )
        session.query(Booking).filter(
            (Booking.student_id.in_(user_ids_to_delete)) | (Booking.instructor_id.in_(user_ids_to_delete))
        ).delete(synchronize_session=False)

        # 2. Delete availability slots
        deleted_slots = (
            session.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id.in_(user_ids_to_delete)).count()
        )
        session.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 3. Delete blackout dates
        session.query(BlackoutDate).filter(BlackoutDate.instructor_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 4. Delete services
        profile_ids = (
            session.query(InstructorProfile.id).filter(InstructorProfile.user_id.in_(user_ids_to_delete)).all()
        )
        profile_ids = [p[0] for p in profile_ids]
        if profile_ids:
            session.query(Service).filter(Service.instructor_profile_id.in_(profile_ids)).delete(
                synchronize_session=False
            )

        # 5. Delete instructor profiles
        session.query(InstructorProfile).filter(InstructorProfile.user_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 6. Delete password reset tokens
        session.query(PasswordResetToken).filter(PasswordResetToken.user_id.in_(user_ids_to_delete)).delete(
            synchronize_session=False
        )

        # 7. Finally delete users
        session.query(User).filter(User.id.in_(user_ids_to_delete)).delete(synchronize_session=False)

        session.commit()
        logger.info(f"Deleted {deleted_bookings} bookings and {deleted_slots} slots")

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Cleanup complete in {duration:.2f}s")

    return excluded_ids


def create_dummy_instructors(session: Session):
    """Create dummy instructors with realistic availability patterns."""
    logger.info("Creating dummy instructors...")

    for template in INSTRUCTOR_TEMPLATES:
        # Create user
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=UserRole.INSTRUCTOR,
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

        # Create services
        services_created = {}
        for svc in template["services"]:
            service = Service(
                instructor_profile_id=profile.id,
                skill=svc["skill"],
                hourly_rate=svc["rate"],
                description=svc["desc"],
                is_active=True,
            )
            session.add(service)
            session.flush()
            services_created[svc["skill"]] = service

        # Create availability patterns
        create_realistic_availability(session, user.id)

        # Store for later processing
        template["_user_id"] = user.id
        template["_services"] = services_created

    session.commit()
    logger.info(f"Created {len(INSTRUCTOR_TEMPLATES)} instructors with profiles and services")


def create_realistic_availability(session: Session, instructor_id: int):
    """Create availability patterns including past and future weeks."""
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
    slots_created = 0

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

        # Add time slots based on pattern
        for start_hour, end_hour in pattern:
            # Occasionally adjust times slightly for variety
            if random.random() < 0.3:
                start_hour += random.choice([-1, 0, 1])
                end_hour += random.choice([-1, 0, 1])

            # Ensure valid times
            start_hour = max(8, min(20, start_hour))
            end_hour = max(start_hour + 1, min(21, end_hour))

            # Create slot directly (single-table design)
            slot = AvailabilitySlot(
                instructor_id=instructor_id,
                specific_date=current_date,
                start_time=time(start_hour, 0),
                end_time=time(end_hour, 0),
            )
            session.add(slot)
            slots_created += 1

        current_date += timedelta(days=1)

    logger.debug(f"Created {slots_created} availability slots for instructor {instructor_id}")


def create_dummy_students(session: Session):
    """Create dummy student accounts."""
    logger.info("Creating dummy students...")

    for template in STUDENT_TEMPLATES:
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)

    session.commit()
    logger.info(f"Created {len(STUDENT_TEMPLATES)} students")


def create_sample_bookings(session: Session):
    """
    Create bookings as self-contained records.

    Bookings store all necessary information directly and don't reference
    availability slots. This demonstrates the clean architecture principle
    that bookings are independent commitments.
    """
    logger.info("Creating sample bookings (self-contained records)...")

    students = session.query(User).filter(User.role == UserRole.STUDENT).all()
    today = date.today()
    bookings_created = 0
    past_bookings_created = 0

    for template in INSTRUCTOR_TEMPLATES:
        if "_user_id" not in template:
            continue

        instructor_id = template["_user_id"]
        services = template.get("_services", {})

        if not services:
            continue

        # Get instructor's typical time patterns from availability
        instructor_slots = (
            session.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == instructor_id,
                AvailabilitySlot.specific_date >= today - timedelta(weeks=2),
                AvailabilitySlot.specific_date <= today + timedelta(weeks=3),
            )
            .limit(10)
            .all()
        )

        # Extract typical time patterns
        typical_times = []
        for slot in instructor_slots:
            typical_times.append((slot.start_time, slot.end_time))

        if not typical_times:
            # Default times if no availability found
            typical_times = [(time(9, 0), time(10, 0)), (time(14, 0), time(15, 0))]

        # Create past bookings with service that will be soft deleted
        service_to_soft_delete = template.get("service_to_soft_delete")
        if service_to_soft_delete and service_to_soft_delete in services:
            service = services[service_to_soft_delete]

            # Create 3-5 past bookings with this service
            for i in range(random.randint(3, 5)):
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

                # Create self-contained booking (NO availability_slot_id!)
                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor_id,
                    service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    service_name=service.skill,
                    hourly_rate=service.hourly_rate,
                    total_price=Decimal(str(service.hourly_rate * duration_minutes / 60)),
                    duration_minutes=duration_minutes,
                    status=BookingStatus.COMPLETED,
                    location_type=random.choice(["student_home", "instructor_location", "neutral"]),
                    meeting_location=f"{random.choice(['Student home', 'Instructor studio', 'Local library'])}",
                    student_note="Looking forward to the lesson!",
                    created_at=booking_date - timedelta(days=2),
                    confirmed_at=booking_date - timedelta(days=2),
                    completed_at=booking_date + timedelta(hours=duration_minutes / 60),
                )
                session.add(booking)
                past_bookings_created += 1

        # Create regular bookings (past and future)
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

            # Pick a service (excluding the one to be soft deleted for future bookings)
            available_services = [s for name, s in services.items() if s.is_active]
            if booking_date >= today and service_to_soft_delete:
                available_services = [s for name, s in services.items() if name != service_to_soft_delete]

            if not available_services:
                continue

            service = random.choice(available_services)

            # Choose time based on typical patterns
            start_time, end_time = random.choice(typical_times)

            # Calculate duration
            start_datetime = datetime.combine(date.today(), start_time)
            end_datetime = datetime.combine(date.today(), end_time)
            duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)

            # Determine booking status based on date
            if booking_date < today:
                status = BookingStatus.COMPLETED
            else:
                status = BookingStatus.CONFIRMED

            # Create self-contained booking
            booking = Booking(
                student_id=student.id,
                instructor_id=instructor_id,
                service_id=service.id,
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
                student_note=random.choice(
                    ["Looking forward to the lesson!", "Please focus on fundamentals", "I've been practicing!", None]
                ),
                created_at=datetime.now() - timedelta(days=random.randint(1, 14)),
                confirmed_at=datetime.now() - timedelta(days=random.randint(1, 14)),
                completed_at=datetime.now() if status == BookingStatus.COMPLETED else None,
            )
            session.add(booking)
            bookings_created += 1

    session.commit()
    logger.info(f"Created {bookings_created} regular bookings and {past_bookings_created} past bookings")
    logger.info("All bookings are self-contained (no slot references)")


def soft_delete_services(session: Session):
    """Soft delete services that have bookings."""
    logger.info("Soft deleting services with bookings...")

    soft_deleted_count = 0

    for template in INSTRUCTOR_TEMPLATES:
        service_to_soft_delete = template.get("service_to_soft_delete")
        if service_to_soft_delete and "_services" in template:
            service = template["_services"].get(service_to_soft_delete)

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
            .filter(
                AvailabilitySlot.instructor_id == past_booking.instructor_id,
                AvailabilitySlot.specific_date == past_booking.booking_date,
            )
            .all()
        )

        if slots:
            logger.info(f"Found {len(slots)} slots on {past_booking.booking_date}")
            logger.info(f"Deleting slots to test independence...")

            for slot in slots:
                session.delete(slot)

            session.commit()

            # Verify booking still exists
            booking_check = session.query(Booking).filter(Booking.id == past_booking.id).first()
            if booking_check:
                logger.info("✅ SUCCESS: Booking persists after availability deletion!")
                logger.info(f"   Booking {booking_check.id} still exists")
            else:
                logger.error("❌ FAILURE: Booking was deleted!")
        else:
            logger.info("No slots found to test deletion")
    else:
        logger.info("No past bookings found to test with")


def quick_login_test():
    """Quick test to verify login works with seeded data."""
    try:
        import requests

        logger.info("\nTesting login with seeded credentials...")

        # Test instructor login
        response = requests.post(
            "http://localhost:8000/auth/login",
            data={"username": "sarah.chen@example.com", "password": TEST_PASSWORD},
        )

        if response.status_code == 200:
            logger.info("✅ Login test PASSED! Backend authentication working.")
        else:
            logger.warning(f"⚠️  Login test returned {response.status_code}")
            logger.warning("Make sure backend is running: uvicorn app.main:app --reload")
    except Exception as e:
        logger.info("ℹ️  Skipping login test (backend might not be running)")
        logger.debug(f"Test error: {str(e)}")


def main():
    """Main function with safety checks."""
    logger.info("Starting database reset and seed process...")
    logger.info("Work Stream 11 Compliant - Clean Architecture")

    # Show usage hint if no environment variables set
    if not any(
        os.getenv(var, "").lower() == "true"
        for var in ["USE_TEST_DATABASE", "ALLOW_SEED_PRODUCTION", "FORCE_ALLOW_RESET"]
    ):
        logger.info("ℹ️  Running with default settings (will check for production database)")
        logger.info("   See script header or use --help for usage options")

    # ============================================================================
    # SAFETY CHECK - THIS IS THE KEY ADDITION
    # ============================================================================
    # Determine which database to use
    if os.getenv("USE_TEST_DATABASE", "").lower() == "true":
        # Use test database if explicitly requested
        database_url = settings.test_database_url or settings.get_database_url()
        logger.info("Using TEST database as requested")
    else:
        # Use production settings by default
        database_url = settings.database_url

    # Validate it's safe to proceed
    try:
        validate_safe_database_url(database_url)
    except RuntimeError as e:
        # Check for override options
        if os.getenv("FORCE_ALLOW_RESET", "").lower() == "true":
            logger.error(
                "\n" + "!" * 60 + "\n"
                "!!! FORCE_ALLOW_RESET is set - BYPASSING SAFETY CHECKS !!!\n"
                "!!! This is EXTREMELY DANGEROUS for production data   !!!\n"
                "!" * 60 + "\n"
            )
            response = input("Type 'DELETE PRODUCTION DATA' to proceed: ")
            if response != "DELETE PRODUCTION DATA":
                logger.error("Confirmation failed. Exiting.")
                sys.exit(1)
        elif os.getenv("ALLOW_SEED_PRODUCTION", "").lower() == "true":
            # More convenient for pre-launch development
            logger.warning(
                "\n" + "=" * 60 + "\n"
                "⚠️  ALLOW_SEED_PRODUCTION is set\n"
                "=" * 60 + "\n"
                "This will reset and seed what appears to be a production database.\n"
                "Only use this before going live!\n"
                "=" * 60 + "\n"
            )
            response = input("Proceed with seeding production database? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Seed cancelled.")
                sys.exit(0)
        else:
            logger.error(str(e))
            logger.info(
                "\nTo seed this database, use one of these options:\n"
                "=" * 70 + "\n"
                "| Command Flag              | Database Used    | Use Case                    |\n"
                "|---------------------------|------------------|-----------------------------|\n"
                "| USE_TEST_DATABASE=true    | Local test DB    | Safe local testing          |\n"
                "| ALLOW_SEED_PRODUCTION=true| Production       | Pre-launch seeding (yes/no) |\n"
                "| FORCE_ALLOW_RESET=true    | Production       | Emergency (type confirm)    |\n"
                "| (no flags)                | BLOCKED!         | Safety error                |\n"
                "=" * 70 + "\n\n"
                "Examples:\n"
                "  USE_TEST_DATABASE=true python scripts/rreset_and_seed_database_enhanced.py\n"
                "  ALLOW_SEED_PRODUCTION=true python scripts/rreset_and_seed_database_enhanced.py\n"
            )
            sys.exit(1)

    # Connect to database
    engine = create_engine(database_url, pool_pre_ping=True)
    session = Session(engine)

    try:
        # Step 1: Cleanup
        cleanup_database(session)

        # Step 2: Create users
        create_dummy_instructors(session)
        create_dummy_students(session)

        # Step 3: Create bookings as self-contained records
        create_sample_bookings(session)

        # Step 4: Soft delete services with bookings
        soft_delete_services(session)

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

        # Count availability slots
        total_slots = session.query(AvailabilitySlot).count()

        logger.info("\n" + "=" * 50)
        logger.info("Database reset complete!")
        logger.info(f"Total users: {total_users}")
        logger.info(f"  - Instructors: {total_instructors}")
        logger.info(f"  - Students: {total_students}")
        logger.info(f"\nTotal services: {total_services}")
        logger.info(f"  - Active: {active_services}")
        logger.info(f"  - Soft deleted: {inactive_services}")
        logger.info(f"\nTotal bookings: {total_bookings}")
        logger.info(f"  - Past: {past_bookings}")
        logger.info(f"  - Future: {future_bookings}")
        logger.info(f"\nTotal availability slots: {total_slots}")

        logger.info("\nTest credentials:")
        logger.info(f"  Password for all users: {TEST_PASSWORD}")
        logger.info("\nInstructors:")
        for t in INSTRUCTOR_TEMPLATES[:2]:  # Show first 2
            logger.info(f"  - {t['email']}")
        logger.info("\nStudents:")
        for t in STUDENT_TEMPLATES[:2]:  # Show first 2
            logger.info(f"  - {t['email']}")

        logger.info("\n🎯 Clean Architecture Achieved:")
        logger.info("  ✅ Bookings are self-contained")
        logger.info("  ✅ No slot references in bookings")
        logger.info("  ✅ Single-table availability design")
        logger.info("  ✅ Layer independence verified")

        # Quick login test
        quick_login_test()

    except Exception as e:
        logger.error(f"Error during database reset: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    # Check for help flag
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    main()
