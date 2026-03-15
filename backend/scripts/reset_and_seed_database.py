#!/usr/bin/env python3
"""
Database reset and seed script for InstaInstru.

This script provides a consistent way to reset the database to a known state
with test data. It preserves specified users while removing all others and
creates a set of diverse instructor profiles with varied availability patterns.

Updated to include test students and sample bookings with location_type field.

Usage:
    python scripts/reset_and_seed_database.py
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import logging  # noqa: E402
from pathlib import Path
import random
import re
import sys

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, func, or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.enums import RoleName
from app.models.address import InstructorServiceArea  # noqa: E402
from app.models.availability import BlackoutDate  # noqa: E402
from app.models.availability_day import AvailabilityDay  # noqa: E402
from app.models.booking import Booking, BookingStatus  # noqa: E402
from app.models.instructor import InstructorPreferredPlace, InstructorProfile  # noqa: E402
from app.models.password_reset import PasswordResetToken  # noqa: E402
from app.models.region_boundary import RegionBoundary  # noqa: E402
from app.models.service_catalog import (  # noqa: E402
    InstructorService as Service,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory  # noqa: E402
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository  # noqa: E402
from app.utils.bitset import bits_from_windows, windows_from_bits  # noqa: E402
from app.utils.location_privacy import jitter_coordinates  # noqa: E402

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
EXCLUDE_FROM_CLEANUP = [
    "mehdisaedi@hotmail.com",  # Keep this user
    # Add more emails here as needed
    "mehdi@saedi.ca",
]

# Test password for all dummy accounts
TEST_PASSWORD = "TestPassword123!"

# NYC areas for instructors
NYC_AREAS = [
    "Manhattan - Upper East Side",
    "Manhattan - Upper West Side",
    "Manhattan - Midtown",
    "Manhattan - Chelsea",
    "Manhattan - Greenwich Village",
    "Manhattan - SoHo",
    "Manhattan - Financial District",
    "Brooklyn - Williamsburg",
    "Brooklyn - Park Slope",
    "Brooklyn - DUMBO",
    "Queens - Astoria",
    "Queens - Long Island City",
]

TEACHING_LOCATIONS = [
    {
        "address": "225 Cherry Street, New York, NY 10002",
        "lat": 40.7128,
        "lng": -74.0060,
        "neighborhood": "Lower East Side, Manhattan",
        "label": "Studio",
    },
    {
        "address": "101 Bedford Ave, Brooklyn, NY 11211",
        "lat": 40.7172,
        "lng": -73.9577,
        "neighborhood": "Williamsburg, Brooklyn",
        "label": "Studio",
    },
    {
        "address": "31-00 47th Ave, Long Island City, NY 11101",
        "lat": 40.7440,
        "lng": -73.9370,
        "neighborhood": "Long Island City, Queens",
        "label": "Studio",
    },
]

SEED_CATEGORY_SLUG = "generated-seed-services"
SEED_SUBCATEGORY_SLUG = "generated-seed-services"

# Test Students
STUDENT_TEMPLATES = [
    {
        "name": "John Smith",
        "email": "john.smith@example.com",
        "interests": ["Yoga", "Spanish", "Cooking"],
        "preferred_areas": ["Manhattan - Upper East Side", "Manhattan - Midtown"],
    },
    {
        "name": "Emma Johnson",
        "email": "emma.johnson@example.com",
        "interests": ["Piano", "Photography", "French"],
        "preferred_areas": ["Brooklyn - Park Slope", "Manhattan - Greenwich Village"],
    },
    {
        "name": "Alex Davis",
        "email": "alex.davis@example.com",
        "interests": ["Personal Training", "Web Development", "Financial Planning"],
        "preferred_areas": ["Manhattan - Chelsea", "Manhattan - Financial District"],
    },
    {
        "name": "Sophia Martinez",
        "email": "sophia.martinez@example.com",
        "interests": ["Makeup Artistry", "Baking", "Meditation"],
        "preferred_areas": ["Brooklyn - Williamsburg", "Queens - Astoria"],
    },
    {
        "name": "William Brown",
        "email": "william.brown@example.com",
        "interests": ["Python Programming", "Day Trading", "HIIT"],
        "preferred_areas": ["Queens - Long Island City", "Manhattan - Midtown"],
    },
]

# Instructor templates (keeping your existing ones)
INSTRUCTOR_TEMPLATES = [
    {
        "name": "Sarah Chen",
        "email": "sarah.chen@example.com",
        "bio": "Certified yoga instructor with 8 years of experience in Vinyasa and Hatha yoga. I believe in creating a peaceful, inclusive environment where students of all levels can explore their practice. Specialized in stress relief and flexibility training.",
        "years_experience": 8,
        "areas": ["Manhattan - Upper East Side", "Manhattan - Midtown"],
        "services": [
            {
                "skill": "Yoga",
                "rate": 85,
                "desc": "Vinyasa and Hatha yoga for all levels",
            },
            {
                "skill": "Meditation",
                "rate": 65,
                "desc": "Guided meditation and mindfulness techniques",
            },
            {
                "skill": "Breathwork",
                "rate": 70,
                "desc": "Pranayama and breathing exercises",
            },
        ],
        "availability_pattern": "mornings",  # Primarily morning classes
    },
    {
        "name": "Michael Rodriguez",
        "email": "michael.rodriguez@example.com",
        "bio": "Professional pianist and music educator with a Master's from Juilliard. I specialize in classical piano but also teach jazz and contemporary styles. My approach focuses on technique, music theory, and creative expression.",
        "years_experience": 12,
        "areas": ["Manhattan - Upper West Side", "Manhattan - Greenwich Village"],
        "services": [
            {
                "skill": "Piano",
                "rate": 120,
                "desc": "Classical, jazz, and contemporary piano",
            },
            {
                "skill": "Music Theory",
                "rate": 95,
                "desc": "Comprehensive music theory and composition",
            },
            {
                "skill": "Sight Reading",
                "rate": 90,
                "desc": "Improve your sight reading skills",
            },
        ],
        "availability_pattern": "evenings",  # Evening lessons after work/school
    },
    {
        "name": "Emily Watson",
        "email": "emily.watson@example.com",
        "bio": "Native Spanish speaker with teaching certification from Instituto Cervantes. I make language learning fun and practical, focusing on conversational skills and cultural immersion. Also fluent in English and French.",
        "years_experience": 6,
        "areas": ["Brooklyn - Park Slope", "Brooklyn - Williamsburg"],
        "services": [
            {
                "skill": "Spanish",
                "rate": 75,
                "desc": "Spanish for all levels - conversation to business",
            },
            {"skill": "ESL", "rate": 70, "desc": "English as a Second Language"},
            {"skill": "French", "rate": 80, "desc": "French language and culture"},
        ],
        "availability_pattern": "flexible",  # Various times throughout the week
    },
    {
        "name": "David Kim",
        "email": "david.kim@example.com",
        "bio": "ACE certified personal trainer specializing in strength training and HIIT. Former college athlete with expertise in sports performance and injury prevention. I create customized workout plans tailored to your goals.",
        "years_experience": 10,
        "areas": ["Manhattan - Chelsea", "Manhattan - SoHo"],
        "services": [
            {
                "skill": "Personal Training",
                "rate": 100,
                "desc": "1-on-1 strength and conditioning",
            },
            {
                "skill": "HIIT",
                "rate": 85,
                "desc": "High-intensity interval training sessions",
            },
            {
                "skill": "Nutrition Coaching",
                "rate": 75,
                "desc": "Personalized nutrition planning",
            },
        ],
        "availability_pattern": "early_bird",  # Early morning and lunch sessions
    },
    {
        "name": "Lisa Thompson",
        "email": "lisa.thompson@example.com",
        "bio": "Professional photographer with 15 years in the industry. From portraits to landscapes, I teach both technical skills and artistic vision. Experienced with DSLR, mirrorless, and film photography.",
        "years_experience": 15,
        "areas": ["Brooklyn - DUMBO", "Manhattan - SoHo"],
        "services": [
            {
                "skill": "Photography",
                "rate": 110,
                "desc": "Digital and film photography techniques",
            },
            {
                "skill": "Photo Editing",
                "rate": 85,
                "desc": "Lightroom and Photoshop mastery",
            },
            {
                "skill": "Portrait Photography",
                "rate": 120,
                "desc": "Professional portrait techniques",
            },
        ],
        "availability_pattern": "weekends",  # Primarily weekends
    },
    {
        "name": "James Park",
        "email": "james.park@example.com",
        "bio": "Full-stack developer with 10+ years in the tech industry. I teach practical coding skills from web development to data science. Patient instructor who breaks down complex concepts into digestible lessons.",
        "years_experience": 10,
        "areas": ["Queens - Long Island City", "Manhattan - Midtown"],
        "services": [
            {
                "skill": "Web Development",
                "rate": 130,
                "desc": "HTML, CSS, JavaScript, React",
            },
            {
                "skill": "Python Programming",
                "rate": 125,
                "desc": "Python for beginners to advanced",
            },
            {
                "skill": "Data Science",
                "rate": 140,
                "desc": "Data analysis with Python and SQL",
            },
        ],
        "availability_pattern": "evenings_weekends",  # After work and weekends
    },
    {
        "name": "Maria Garcia",
        "email": "maria.garcia@example.com",
        "bio": "Professional chef with experience in Michelin-starred restaurants. I teach cooking techniques from basic knife skills to advanced culinary arts. Specializing in Mediterranean and Latin American cuisine.",
        "years_experience": 18,
        "areas": ["Queens - Astoria", "Manhattan - Upper West Side"],
        "services": [
            {
                "skill": "Cooking",
                "rate": 95,
                "desc": "From basics to gourmet techniques",
            },
            {"skill": "Baking", "rate": 90, "desc": "Breads, pastries, and desserts"},
            {
                "skill": "Meal Prep",
                "rate": 80,
                "desc": "Efficient and healthy meal preparation",
            },
        ],
        "availability_pattern": "variable",  # Changes week to week
    },
    {
        "name": "Robert Chang",
        "email": "robert.chang@example.com",
        "bio": "CFA charterholder with 20 years on Wall Street. I demystify finance and investing for individuals looking to take control of their financial future. From budgeting basics to advanced investment strategies.",
        "years_experience": 20,
        "areas": ["Manhattan - Financial District", "Manhattan - Midtown"],
        "services": [
            {
                "skill": "Financial Planning",
                "rate": 150,
                "desc": "Personal finance and budgeting",
            },
            {
                "skill": "Investment Strategy",
                "rate": 175,
                "desc": "Portfolio management and analysis",
            },
            {
                "skill": "Day Trading",
                "rate": 200,
                "desc": "Technical analysis and trading strategies",
            },
        ],
        "availability_pattern": "business_hours",  # Standard business hours
    },
    {
        "name": "Amanda Foster",
        "email": "amanda.foster@example.com",
        "bio": "Licensed esthetician and makeup artist for TV and film. I teach both everyday makeup techniques and special effects. Passionate about helping people feel confident and beautiful in their own skin.",
        "years_experience": 9,
        "areas": ["Manhattan - Chelsea", "Brooklyn - Williamsburg"],
        "services": [
            {
                "skill": "Makeup Artistry",
                "rate": 90,
                "desc": "From natural looks to glam",
            },
            {"skill": "Skincare", "rate": 85, "desc": "Personalized skincare routines"},
            {
                "skill": "Special Effects",
                "rate": 110,
                "desc": "SFX makeup for film and events",
            },
        ],
        "availability_pattern": "afternoons",  # Afternoon appointments
    },
    {
        "name": "Kevin Liu",
        "email": "kevin.liu@example.com",
        "bio": "Native Mandarin speaker with a PhD in Chinese Literature. I combine language instruction with cultural education, using immersive techniques to accelerate learning. Also teach Chinese calligraphy and history.",
        "years_experience": 7,
        "areas": ["Manhattan - Chinatown", "Queens - Flushing"],
        "services": [
            {
                "skill": "Mandarin Chinese",
                "rate": 85,
                "desc": "All levels - pinyin to business Chinese",
            },
            {
                "skill": "Calligraphy",
                "rate": 70,
                "desc": "Traditional Chinese calligraphy",
            },
            {
                "skill": "Chinese Culture",
                "rate": 65,
                "desc": "History, customs, and traditions",
            },
        ],
        "availability_pattern": "mixed",  # Mix of different times
    },
]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "seeded-service"


def _get_or_create_seed_subcategory(session: Session) -> ServiceSubcategory:
    category = session.query(ServiceCategory).filter(ServiceCategory.slug == SEED_CATEGORY_SLUG).first()
    if category is None:
        category = ServiceCategory(
            name="Generated Seed Services",
            slug=SEED_CATEGORY_SLUG,
            description="Catalog services generated by reset_and_seed_database.py",
        )
        session.add(category)
        session.flush()

    subcategory = (
        session.query(ServiceSubcategory)
        .filter(
            ServiceSubcategory.category_id == category.id,
            ServiceSubcategory.slug == SEED_SUBCATEGORY_SLUG,
        )
        .first()
    )
    if subcategory is None:
        subcategory = ServiceSubcategory(
            category_id=category.id,
            name="Generated Seed Services",
            slug=SEED_SUBCATEGORY_SLUG,
            description="Subcategory for generated seed services",
            display_order=999,
            is_active=True,
        )
        session.add(subcategory)
        session.flush()

    return subcategory


def _get_or_create_catalog_service(
    session: Session, service_name: str, description: str
) -> ServiceCatalog:
    normalized_name = service_name.strip()
    existing = (
        session.query(ServiceCatalog)
        .filter(func.lower(ServiceCatalog.name) == normalized_name.lower())
        .first()
    )
    if existing is not None:
        return existing

    subcategory = _get_or_create_seed_subcategory(session)
    catalog_service = ServiceCatalog(
        subcategory_id=subcategory.id,
        name=normalized_name,
        slug=_slugify(normalized_name),
        description=description,
        default_duration_minutes=60,
        is_active=True,
    )
    session.add(catalog_service)
    session.flush()
    return catalog_service


def _service_name(service: Service) -> str:
    if service.catalog_entry and service.catalog_entry.name:
        return str(service.catalog_entry.name)
    return "Unknown Service"


def _service_duration_minutes(service: Service) -> int:
    duration_options = getattr(service, "duration_options", None) or [60]
    return int(random.choice(list(duration_options)))


def _build_booking_time_fields(
    booking_date: date,
    start_time: time,
    end_time: time,
) -> dict[str, datetime | str]:
    end_date = booking_date + timedelta(days=1) if end_time == time(0, 0) and start_time != time(0, 0) else booking_date
    booking_start_utc = datetime.combine(  # tz-pattern-ok: seed helper intentionally materializes UTC timestamps
        booking_date, start_time, tzinfo=timezone.utc
    )
    booking_end_utc = datetime.combine(  # tz-pattern-ok: seed helper intentionally materializes UTC timestamps
        end_date, end_time, tzinfo=timezone.utc
    )
    return {
        "booking_start_utc": booking_start_utc,
        "booking_end_utc": booking_end_utc,
        "lesson_timezone": "UTC",
        "instructor_tz_at_booking": "America/New_York",
        "student_tz_at_booking": "America/New_York",
    }


def cleanup_database(session: Session):
    """Remove all users except those in the exclude list."""
    logger.info("Starting database cleanup...")

    # Get users to exclude
    excluded_users = session.query(User).filter(User.email.in_(EXCLUDE_FROM_CLEANUP)).all()

    excluded_ids = [user.id for user in excluded_users]
    logger.info(f"Preserving {len(excluded_ids)} users: {[u.email for u in excluded_users]}")

    # First, delete related data for users we're going to remove
    users_to_delete = session.query(User).filter(~User.id.in_(excluded_ids)).all()

    users_to_delete_ids = [user.id for user in users_to_delete]

    if users_to_delete_ids:
        # Delete in order to respect foreign key constraints

        # 1. Delete bookings
        booking_count = (
            session.query(Booking)
            .filter(
                or_(
                    Booking.student_id.in_(users_to_delete_ids),
                    Booking.instructor_id.in_(users_to_delete_ids),
                )
            )
            .delete(synchronize_session=False)
        )

        # 2. Delete bitmap availability days
        avail_count = (
            session.query(AvailabilityDay)
            .filter(AvailabilityDay.instructor_id.in_(users_to_delete_ids))
            .delete(synchronize_session=False)
        )

        # 3. Delete blackout dates
        blackout_count = (
            session.query(BlackoutDate)
            .filter(BlackoutDate.instructor_id.in_(users_to_delete_ids))
            .delete(synchronize_session=False)
        )

        # 7. Get instructor profile IDs for users to delete
        profile_ids = (
            session.query(InstructorProfile.id).filter(InstructorProfile.user_id.in_(users_to_delete_ids)).all()
        )
        profile_ids = [p[0] for p in profile_ids]

        # 8. Delete services
        if profile_ids:
            service_count = (
                session.query(Service)
                .filter(Service.instructor_profile_id.in_(profile_ids))
                .delete(synchronize_session=False)
            )
        else:
            service_count = 0

        # 9. Delete instructor profiles
        profile_count = (
            session.query(InstructorProfile)
            .filter(InstructorProfile.user_id.in_(users_to_delete_ids))
            .delete(synchronize_session=False)
        )

        # 10. Delete password reset tokens
        token_count = (
            session.query(PasswordResetToken)
            .filter(PasswordResetToken.user_id.in_(users_to_delete_ids))
            .delete(synchronize_session=False)
        )

        # 11. Finally, delete the users
        user_count = session.query(User).filter(User.id.in_(users_to_delete_ids)).delete(synchronize_session=False)

        session.commit()

        logger.info("Cleanup complete:")
        logger.info(f"  - Deleted {user_count} users")
        logger.info(f"  - Deleted {profile_count} instructor profiles")
        logger.info(f"  - Deleted {service_count} services")
        logger.info(f"  - Deleted {avail_count} availability day entries")
        logger.info(f"  - Deleted {blackout_count} blackout dates")
        logger.info(f"  - Deleted {booking_count} bookings")
        logger.info(f"  - Deleted {token_count} password reset tokens")
    else:
        logger.info("No users to delete")

    return excluded_ids


def _time_to_hhmmss(t: time) -> str:
    """Convert a time object to 'HH:MM:00' string for bits_from_windows."""
    return f"{t.hour:02d}:{t.minute:02d}:00"


def create_availability_pattern(session: Session, instructor_id: str, pattern: str, weeks_ahead: int = 12):
    """Create bitmap availability based on pattern type."""
    today = date.today()  # tz-pattern-ok: seed script generates test data
    current_monday = today - timedelta(days=today.weekday())
    repo = AvailabilityDayRepository(session)

    patterns = {
        "mornings": {
            "days": [0, 1, 2, 3, 4, 5, 6],
            "windows": [("08:00:00", "12:00:00")],
        },
        "evenings": {
            "days": [0, 1, 2, 3, 4],
            "windows": [("17:00:00", "21:00:00")],
        },
        "early_bird": {
            "days": [0, 1, 2, 3, 4],
            "windows": [("06:00:00", "09:00:00"), ("12:00:00", "13:00:00")],
        },
        "weekends": {
            "days": [5, 6],
            "windows": [("09:00:00", "17:00:00")],
        },
        "business_hours": {
            "days": [0, 1, 2, 3, 4],
            "windows": [("09:00:00", "17:00:00")],
        },
        "afternoons": {
            "days": [0, 1, 2, 3, 4, 5],
            "windows": [("13:00:00", "18:00:00")],
        },
        "evenings_weekends": {
            "days": [0, 1, 2, 3, 4],
            "windows": [("18:00:00", "21:00:00")],
            "weekend_windows": [("10:00:00", "16:00:00")],
        },
        "flexible": {"random": True},
        "variable": {"random": True, "sparse": True},
        "mixed": {"random": True, "mixed": True},
    }

    pattern_config = patterns.get(pattern, patterns["flexible"])

    for week_offset in range(weeks_ahead):
        week_start = current_monday + timedelta(weeks=week_offset)

        if random.random() < 0.1:
            blackout_day = week_start + timedelta(days=random.randint(0, 6))
            if blackout_day > today:
                blackout = BlackoutDate(
                    instructor_id=instructor_id,
                    date=blackout_day,
                    reason="Personal day",
                )
                session.add(blackout)
            continue

        items = []

        if pattern_config.get("random"):
            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                if current_date <= today:
                    continue
                if pattern_config.get("sparse") and random.random() < 0.6:
                    continue
                elif not pattern_config.get("sparse") and random.random() < 0.3:
                    continue

                if pattern_config.get("mixed"):
                    slot_type = random.choice(["morning", "afternoon", "evening"])
                    if slot_type == "morning":
                        windows = [(_time_to_hhmmss(time(random.randint(7, 9), 0)), _time_to_hhmmss(time(random.randint(10, 12), 0)))]
                    elif slot_type == "afternoon":
                        windows = [(_time_to_hhmmss(time(random.randint(12, 14), 0)), _time_to_hhmmss(time(random.randint(15, 17), 0)))]
                    else:
                        windows = [(_time_to_hhmmss(time(random.randint(17, 19), 0)), _time_to_hhmmss(time(random.randint(20, 21), 0)))]
                else:
                    num_windows = random.randint(1, 3)
                    windows = []
                    start_hour = 8
                    for _ in range(num_windows):
                        duration = random.choice([1, 2, 3])
                        if start_hour + duration <= 20:
                            windows.append((_time_to_hhmmss(time(start_hour, 0)), _time_to_hhmmss(time(start_hour + duration, 0))))
                            start_hour += duration + random.randint(1, 2)

                items.append((current_date, bits_from_windows(windows)))
        else:
            days = pattern_config["days"]
            windows = pattern_config["windows"]

            for day_offset in days:
                current_date = week_start + timedelta(days=day_offset)
                if current_date <= today:
                    continue
                if random.random() < 0.05:
                    continue

                if pattern == "evenings_weekends" and day_offset in [5, 6]:
                    day_windows = pattern_config.get("weekend_windows", windows)
                else:
                    day_windows = windows

                items.append((current_date, bits_from_windows(day_windows)))

        if items:
            repo.upsert_week(instructor_id, items)

    session.commit()


def create_dummy_students(session: Session):
    """Create dummy student accounts."""
    logger.info("Creating dummy students...")

    created_count = 0

    for template in STUDENT_TEMPLATES:
        # Check if user already exists
        existing = session.query(User).filter(User.email == template["email"]).first()
        if existing:
            logger.info(f"User {template['email']} already exists, skipping...")
            continue

        # Create user
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=RoleName.STUDENT,
            is_active=True,
        )
        session.add(user)
        session.flush()

        created_count += 1
        logger.info(f"Created student: {template['name']} ({template['email']})")

    session.commit()
    logger.info(f"Created {created_count} dummy students")


def create_dummy_instructors(session: Session):
    """Create dummy instructor accounts with profiles and availability."""
    logger.info("Creating dummy instructors...")

    created_count = 0

    for template in INSTRUCTOR_TEMPLATES:
        # Check if user already exists
        existing = session.query(User).filter(User.email == template["email"]).first()
        if existing:
            logger.info(f"User {template['email']} already exists, skipping...")
            continue

        # Create user
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=RoleName.INSTRUCTOR,
            is_active=True,
        )
        session.add(user)
        session.flush()

        # Create instructor profile
        profile = InstructorProfile(
            user_id=user.id,
            bio=template["bio"],
            years_experience=template["years_experience"],
            non_travel_buffer_minutes=random.choice([0, 15, 30]),
            travel_buffer_minutes=random.choice([60, 75, 90]),
            overnight_protection_enabled=True,
        )
        session.add(profile)
        session.flush()

        teaching_location = random.choice(TEACHING_LOCATIONS)
        approx_lat, approx_lng = jitter_coordinates(
            teaching_location["lat"], teaching_location["lng"]
        )
        session.add(
            InstructorPreferredPlace(
                instructor_id=user.id,
                kind="teaching_location",
                address=teaching_location["address"],
                label=teaching_location.get("label"),
                position=0,
                lat=teaching_location["lat"],
                lng=teaching_location["lng"],
                approx_lat=approx_lat,
                approx_lng=approx_lng,
                neighborhood=teaching_location.get("neighborhood"),
            )
        )

        for area_name in template.get("areas", []):
            neighborhood = (
                session.query(RegionBoundary)
                .filter(RegionBoundary.region_type == "nyc", RegionBoundary.region_name == area_name)
                .first()
            )
            if neighborhood:
                session.add(
                    InstructorServiceArea(
                        instructor_id=user.id,
                        neighborhood_id=neighborhood.id,
                        coverage_type="primary",
                    )
                )

        # Create services
        for svc in template["services"]:
            catalog_service = _get_or_create_catalog_service(session, svc["skill"], svc["desc"])
            service = Service(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                format_prices=[
                    {"format": "student_location", "hourly_rate": svc["rate"]},
                    {"format": "instructor_location", "hourly_rate": svc["rate"]},
                    {"format": "online", "hourly_rate": svc["rate"]},
                ],
                description=svc["desc"],
                duration_options=[random.choice([45, 60, 90])],
            )
            service.catalog_entry = catalog_service
            session.add(service)

        # Create availability pattern
        create_availability_pattern(session, user.id, template["availability_pattern"])

        created_count += 1
        logger.info(f"Created instructor: {template['name']} ({template['email']})")

    session.commit()
    logger.info(f"Created {created_count} dummy instructors")


def create_sample_bookings(session: Session):
    """Create sample bookings between students and instructors."""
    logger.info("Creating sample bookings...")

    # Get all students and instructors
    students = session.query(User).filter(User.role == RoleName.STUDENT).all()
    instructors = session.query(User).filter(User.role == RoleName.INSTRUCTOR).all()

    if not students or not instructors:
        logger.warning("No students or instructors found, skipping bookings")
        return

    booking_count = 0
    today = date.today()

    # Create bookings for each student
    for student in students:
        # Get student's preferred services based on interests
        student_template = next((s for s in STUDENT_TEMPLATES if s["email"] == student.email), None)
        if not student_template:
            continue

        interests = student_template["interests"]

        # Create a mix of past, upcoming, and cancelled bookings
        # Past completed bookings
        for i in range(2):
            past_date = today - timedelta(days=random.randint(7, 30))
            booking = create_booking_for_date(session, student, interests, past_date, "past")
            if booking:
                booking_count += 1

        # Upcoming bookings
        for i in range(3):
            future_date = today + timedelta(days=random.randint(1, 14))
            booking = create_booking_for_date(session, student, interests, future_date, "future")
            if booking:
                booking_count += 1

        # Cancelled bookings (mix of past and future)
        for i in range(1):
            cancel_date = today + timedelta(days=random.randint(-10, 10))
            booking = create_booking_for_date(session, student, interests, cancel_date, "cancelled")
            if booking:
                booking_count += 1

    session.commit()
    logger.info(f"Created {booking_count} sample bookings")


def create_booking_for_date(session, student, interests, target_date, booking_type):
    """Helper function to create a booking for a specific date."""
    # Pick a random interest
    interest = random.choice(interests)

    # Find instructors who offer this service
    matching_services = session.query(Service).filter(Service.skill == interest).all()

    if not matching_services:
        return None

    # Pick a random service
    service = random.choice(matching_services)
    instructor_id = service.instructor_profile.user_id

    # Ensure bitmap availability exists for this date
    repo = AvailabilityDayRepository(session)
    existing_bits = repo.get_day_bits(instructor_id, target_date)
    if not existing_bits or not any(existing_bits):
        time_windows = [
            ("09:00:00", "10:00:00"),
            ("10:30:00", "11:30:00"),
            ("14:00:00", "15:00:00"),
            ("16:00:00", "17:00:00"),
            ("18:00:00", "19:00:00"),
        ]
        selected = random.sample(time_windows, random.randint(2, 4))
        repo.upsert_week(instructor_id, [(target_date, bits_from_windows(selected))])
        session.flush()

    # Read back actual availability and pick a booking window from it
    stored_bits = repo.get_day_bits(instructor_id, target_date)
    if not stored_bits or not any(stored_bits):
        return None
    actual_windows = windows_from_bits(bytes(stored_bits))
    if not actual_windows:
        return None
    chosen_win = random.choice(actual_windows)
    # Parse "HH:MM:SS" strings back to time objects
    s_parts = chosen_win[0].split(":")
    e_parts = chosen_win[1].split(":")
    booking_start = time(int(s_parts[0]), int(s_parts[1]))
    booking_end = time(int(e_parts[0]), int(e_parts[1]))

    # Calculate booking details
    duration_minutes = _service_duration_minutes(service)
    hours = duration_minutes / 60

    if booking_type == "past":
        status = BookingStatus.COMPLETED
        completed_at = datetime.combine(target_date, booking_end)  # tz-pattern-ok: seed script generates test data
        cancelled_at = None
        cancelled_by = None
        cancellation_reason = None
    elif booking_type == "cancelled":
        status = BookingStatus.CANCELLED
        completed_at = None
        cancelled_at = datetime.now() - timedelta(days=random.randint(1, 5))
        cancelled_by = random.choice([student.id, instructor_id])
        cancellation_reason = random.choice(
            [
                "Schedule conflict",
                "Feeling unwell",
                "Emergency came up",
                "Need to reschedule",
            ]
        )
    else:  # future
        status = BookingStatus.CONFIRMED
        completed_at = None
        cancelled_at = None
        cancelled_by = None
        cancellation_reason = None

    # Determine location type and meeting location
    location_types = ["student_location", "instructor_location", "neutral_location"]
    location_type = random.choice(location_types)

    area = "NYC"
    service_area = (
        session.query(InstructorServiceArea)
        .join(RegionBoundary, InstructorServiceArea.neighborhood_id == RegionBoundary.id)
        .filter(InstructorServiceArea.instructor_id == instructor_id)
        .first()
    )
    if service_area and service_area.neighborhood:
        area = service_area.neighborhood.region_name or service_area.neighborhood.parent_region or "NYC"

    if location_type == "student_location":
        meeting_location = f"Student's home in {area}"
    elif location_type == "instructor_location":
        meeting_location = f"Instructor's studio in {area}"
    else:  # neutral_location
        neutral_locations = [
            f"Starbucks at {area}",
            f"Public Library in {area}",
            f"{area} Community Center",
            f"Central Park near {area}",
            f"Bryant Park (near {area})",
        ]
        meeting_location = random.choice(neutral_locations)

    # Resolve rate for chosen location type
    booking_rate = service.hourly_rate_for_location_type(location_type)
    total_price = float(booking_rate) * hours

    # Create booking
    booking_time_fields = _build_booking_time_fields(target_date, booking_start, booking_end)
    booking = Booking(
        student_id=student.id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        booking_date=target_date,
        start_time=booking_start,
        end_time=booking_end,
        service_name=_service_name(service),
        hourly_rate=booking_rate,
        total_price=Decimal(str(total_price)),
        duration_minutes=duration_minutes,
        status=status,
        service_area=area,
        meeting_location=meeting_location,
        location_address=meeting_location,
        location_type=location_type,  # NEW FIELD
        student_note=random.choice(
            [
                "Looking forward to the lesson!",
                "First time trying this, excited!",
                "Continuing from last session",
                "Please focus on fundamentals",
                "Need help with specific techniques",
                None,
            ]
        ),
        instructor_note="Great progress today!" if status == BookingStatus.COMPLETED else None,
        completed_at=completed_at,
        cancelled_at=cancelled_at,
        cancelled_by_id=cancelled_by,
        cancellation_reason=cancellation_reason,
        **booking_time_fields,
    )

    session.add(booking)
    session.flush()

    logger.info(
        f"Created {booking_type} booking: {student.full_name} -> {_service_name(service)} on {target_date} ({status}) at {location_type}"
    )

    return booking


def main():
    """Main function to reset and seed the database."""
    logger.info("Starting database reset and seed process...")

    # Create engine and session
    engine = create_engine(settings.database_url)
    session = Session(engine)

    try:
        # Step 1: Cleanup
        excluded_ids = cleanup_database(session)

        # Step 2: Create dummy instructors
        create_dummy_instructors(session)

        # Step 3: Create dummy students
        create_dummy_students(session)

        # Step 4: Create sample bookings
        create_sample_bookings(session)

        # Step 5: Summary
        total_users = session.query(User).count()
        total_instructors = session.query(User).filter(User.role == RoleName.INSTRUCTOR).count()
        total_students = session.query(User).filter(User.role == RoleName.STUDENT).count()
        total_bookings = session.query(Booking).count()
        upcoming_bookings = (
            session.query(Booking)
            .filter(
                Booking.booking_date >= date.today(),
                Booking.status == BookingStatus.CONFIRMED,
            )
            .count()
        )

        logger.info("\n" + "=" * 50)
        logger.info("Database reset complete!")
        logger.info(f"Total users: {total_users}")
        logger.info(f"  - Instructors: {total_instructors}")
        logger.info(f"  - Students: {total_students}")
        logger.info(f"  - Preserved users: {len(excluded_ids)}")
        logger.info(f"Total bookings: {total_bookings}")
        logger.info(f"  - Upcoming: {upcoming_bookings}")
        logger.info("=" * 50)

        logger.info("\nTest credentials for dummy accounts:")
        logger.info(f"Password for all test accounts: {TEST_PASSWORD}")
        logger.info("\nSample student logins:")
        for template in STUDENT_TEMPLATES[:3]:
            logger.info(f"  - {template['email']}")
        logger.info("\nSample instructor logins:")
        for template in INSTRUCTOR_TEMPLATES[:3]:
            logger.info(f"  - {template['email']}")

    except Exception as e:
        logger.error(f"Error during database reset: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
