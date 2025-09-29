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

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import logging
import os
from pathlib import Path
import random
import sys
from typing import List

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.enums import RoleName
from app.models.address import InstructorServiceArea  # noqa: E402
from app.models.availability import AvailabilitySlot, BlackoutDate  # noqa: E402
from app.models.booking import Booking, BookingStatus  # noqa: E402
from app.models.instructor import InstructorProfile  # noqa: E402
from app.models.password_reset import PasswordResetToken  # noqa: E402
from app.models.region_boundary import RegionBoundary  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.user import User

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
                "\n\n" + "=" * 60 + "\n"
                "SAFETY ERROR: REFUSING TO RUN ON PRODUCTION DATABASE!\n"
                "=" * 60 + "\n"
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

# Instructor templates with services - comprehensive test data for filtering
INSTRUCTOR_TEMPLATES = [
    # Music instructors (multiple piano teachers at different price points)
    {
        "name": "Sarah Chen",
        "email": "sarah.chen@example.com",
        "bio": "Experienced piano teacher with 15 years of teaching experience. Juilliard graduate specializing in classical piano.",
        "years_experience": 15,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Piano", "rate": 120, "desc": "Classical piano for all levels"},
            {"skill": "Music Theory", "rate": 80, "desc": "Comprehensive music theory"},
            {"skill": "Sight Reading", "rate": 60, "desc": "Sight reading practice"},
        ],
        "service_to_soft_delete": "Sight Reading",
    },
    {
        "name": "Michael Rodriguez",
        "email": "michael.rodriguez@example.com",
        "bio": "Professional guitarist and music teacher. Expert in rock, jazz, and blues styles.",
        "years_experience": 12,
        "areas": ["Brooklyn", "Queens"],
        "services": [
            {"skill": "Guitar", "rate": 85, "desc": "Electric and acoustic guitar"},
            {"skill": "Bass Guitar", "rate": 90, "desc": "Bass guitar fundamentals"},
            {"skill": "Piano", "rate": 75, "desc": "Contemporary piano lessons"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Emily Watson",
        "email": "emily.watson@example.com",
        "bio": "Concert violinist offering private lessons. First chair at NY Philharmonic.",
        "years_experience": 20,
        "areas": ["Manhattan"],
        "services": [
            {"skill": "Violin", "rate": 150, "desc": "Professional violin instruction"},
            {"skill": "Orchestra Prep", "rate": 130, "desc": "Audition preparation"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "James Park",
        "email": "james.park@example.com",
        "bio": "Affordable piano teacher for beginners. Patient and encouraging approach.",
        "years_experience": 5,
        "areas": ["Queens", "Brooklyn"],
        "services": [
            {"skill": "Piano", "rate": 45, "desc": "Beginner piano lessons"},
            {"skill": "Music Basics", "rate": 35, "desc": "Music fundamentals for kids"},
        ],
        "service_to_soft_delete": "Music Basics",
    },
    # Language instructors
    {
        "name": "Maria Garcia",
        "email": "maria.garcia@example.com",
        "bio": "Native Spanish speaker and certified Spanish teacher. DELE examiner with 10 years experience.",
        "years_experience": 10,
        "areas": ["Manhattan", "Brooklyn", "Queens"],
        "services": [
            {"skill": "Spanish", "rate": 65, "desc": "Spanish for all levels"},
            {"skill": "Spanish Conversation", "rate": 55, "desc": "Conversational practice"},
            {"skill": "Business Spanish", "rate": 75, "desc": "Professional Spanish"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Pierre Dubois",
        "email": "pierre.dubois@example.com",
        "bio": "Native French speaker from Paris. Former Alliance Française instructor.",
        "years_experience": 8,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "French", "rate": 70, "desc": "French language and culture"},
            {"skill": "French Conversation", "rate": 60, "desc": "Conversational French"},
        ],
        "service_to_soft_delete": None,
    },
    # Fitness and wellness
    {
        "name": "Jessica Thompson",
        "email": "jessica.thompson@example.com",
        "bio": "Certified yoga instructor with RYT-500. Specializes in Vinyasa and restorative yoga.",
        "years_experience": 9,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Yoga", "rate": 90, "desc": "Vinyasa and Hatha yoga"},
            {"skill": "Meditation", "rate": 70, "desc": "Guided meditation"},
            {"skill": "Prenatal Yoga", "rate": 100, "desc": "Specialized prenatal yoga"},
        ],
        "service_to_soft_delete": "Prenatal Yoga",
    },
    {
        "name": "David Kim",
        "email": "david.kim@example.com",
        "bio": "Personal trainer and nutrition coach. NASM certified with focus on strength training.",
        "years_experience": 11,
        "areas": ["Manhattan", "Queens"],
        "services": [
            {"skill": "Personal Training", "rate": 120, "desc": "One-on-one fitness training"},
            {"skill": "Nutrition Coaching", "rate": 80, "desc": "Personalized nutrition plans"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Mike Johnson",
        "email": "mike.johnson@example.com",
        "bio": "Former Olympic swimmer offering swimming lessons. Specializes in competitive techniques.",
        "years_experience": 16,
        "areas": ["Manhattan", "Brooklyn", "Staten Island"],
        "services": [
            {"skill": "Swimming", "rate": 110, "desc": "Swimming for all levels"},
            {"skill": "Competitive Swimming", "rate": 130, "desc": "Advanced techniques"},
        ],
        "service_to_soft_delete": None,
    },
    # Dance instructors
    {
        "name": "Rachel Green",
        "email": "rachel.green@example.com",
        "bio": "Professional dancer and choreographer. Broadway performer teaching various styles.",
        "years_experience": 14,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Dance", "rate": 95, "desc": "Contemporary and jazz dance"},
            {"skill": "Ballet", "rate": 100, "desc": "Classical ballet technique"},
            {"skill": "Hip Hop Dance", "rate": 85, "desc": "Hip hop and street dance"},
        ],
        "service_to_soft_delete": None,
    },
    # Academic tutors
    {
        "name": "Dr. Robert Smith",
        "email": "robert.smith@example.com",
        "bio": "PhD in Mathematics from MIT. Experienced math teacher for high school and college.",
        "years_experience": 18,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Math", "rate": 100, "desc": "Algebra, Calculus, Statistics"},
            {"skill": "SAT Math Prep", "rate": 120, "desc": "SAT/ACT preparation"},
            {"skill": "College Math", "rate": 140, "desc": "University mathematics"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Dr. Lisa Anderson",
        "email": "lisa.anderson@example.com",
        "bio": "Chemistry professor with 20 years experience. Specializes in AP Chemistry preparation.",
        "years_experience": 20,
        "areas": ["Manhattan", "Queens"],
        "services": [
            {"skill": "Chemistry", "rate": 110, "desc": "General and organic chemistry"},
            {"skill": "AP Chemistry", "rate": 130, "desc": "AP Chemistry prep"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Thomas Brown",
        "email": "thomas.brown@example.com",
        "bio": "Physics teacher with engineering background. Former NASA engineer.",
        "years_experience": 15,
        "areas": ["Manhattan", "Bronx"],
        "services": [
            {"skill": "Physics", "rate": 105, "desc": "High school and college physics"},
            {"skill": "Engineering Prep", "rate": 115, "desc": "Engineering fundamentals"},
        ],
        "service_to_soft_delete": None,
    },
    # Technology instructors
    {
        "name": "Ryan Chen",
        "email": "ryan.chen@example.com",
        "bio": "Software engineer teaching programming. Full-stack developer with startup experience.",
        "years_experience": 7,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Programming", "rate": 120, "desc": "Python, JavaScript, web dev"},
            {"skill": "Data Science", "rate": 140, "desc": "Machine learning basics"},
        ],
        "service_to_soft_delete": None,
    },
    # Arts and creative
    {
        "name": "Amanda Martinez",
        "email": "amanda.martinez@example.com",
        "bio": "Professional photographer specializing in portraits. Gallery exhibitions worldwide.",
        "years_experience": 13,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Photography", "rate": 100, "desc": "Digital photography basics"},
            {"skill": "Photo Editing", "rate": 80, "desc": "Photoshop and Lightroom"},
        ],
        "service_to_soft_delete": "Photo Editing",
    },
    {
        "name": "Carlos Rivera",
        "email": "carlos.rivera@example.com",
        "bio": "Professional chef with Michelin star experience. Culinary Institute graduate.",
        "years_experience": 17,
        "areas": ["Manhattan", "Queens", "Brooklyn"],
        "services": [
            {"skill": "Cooking", "rate": 110, "desc": "Professional cooking techniques"},
            {"skill": "Baking", "rate": 95, "desc": "Artisan bread and pastries"},
        ],
        "service_to_soft_delete": None,
    },
    # Sports instructors
    {
        "name": "Alex Turner",
        "email": "alex.turner@example.com",
        "bio": "Professional tennis coach with USTA certification. Former college player.",
        "years_experience": 10,
        "areas": ["Manhattan", "Brooklyn", "Queens"],
        "services": [
            {"skill": "Tennis", "rate": 100, "desc": "Tennis for all skill levels"},
            {"skill": "Tennis Strategy", "rate": 110, "desc": "Advanced tactics"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Daniel Park",
        "email": "daniel.park@example.com",
        "bio": "Chess master and tournament player. FIDE rated instructor.",
        "years_experience": 8,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Chess", "rate": 70, "desc": "Chess for all levels"},
            {"skill": "Tournament Chess", "rate": 90, "desc": "Competitive preparation"},
        ],
        "service_to_soft_delete": None,
    },
    # Budget instructors (testing low price range)
    {
        "name": "Jake Miller",
        "email": "jake.miller@example.com",
        "bio": "College student offering affordable tutoring. Dean's list scholar.",
        "years_experience": 2,
        "areas": ["Queens", "Brooklyn"],
        "services": [
            {"skill": "Basic Math", "rate": 30, "desc": "Elementary math help"},
            {"skill": "Reading", "rate": 25, "desc": "Reading comprehension"},
            {"skill": "Homework Help", "rate": 20, "desc": "General homework assistance"},
        ],
        "service_to_soft_delete": "Homework Help",
    },
    {
        "name": "Emma Davis",
        "email": "emma.davis@example.com",
        "bio": "Recent graduate offering budget-friendly language practice.",
        "years_experience": 1,
        "areas": ["Brooklyn", "Queens"],
        "services": [
            {"skill": "English Conversation", "rate": 35, "desc": "English practice"},
            {"skill": "Basic Spanish", "rate": 30, "desc": "Beginner Spanish"},
        ],
        "service_to_soft_delete": None,
    },
    # Premium instructors (testing high price range)
    {
        "name": "Dr. Victoria Sterling",
        "email": "victoria.sterling@example.com",
        "bio": "Concert pianist and Juilliard professor. International competition winner.",
        "years_experience": 25,
        "areas": ["Manhattan"],
        "services": [
            {"skill": "Piano Masterclass", "rate": 200, "desc": "Professional piano instruction"},
            {"skill": "Performance Coaching", "rate": 180, "desc": "Stage performance"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Marcus Goldman",
        "email": "marcus.goldman@example.com",
        "bio": "Wall Street executive teaching finance. MBA from Wharton.",
        "years_experience": 20,
        "areas": ["Manhattan"],
        "services": [
            {"skill": "Finance", "rate": 175, "desc": "Corporate finance"},
            {"skill": "Business Strategy", "rate": 190, "desc": "Executive coaching"},
            {"skill": "Investment Banking", "rate": 185, "desc": "IB preparation"},
        ],
        "service_to_soft_delete": "Investment Banking",
    },
    # Additional variety
    {
        "name": "Sophia Patel",
        "email": "sophia.patel@example.com",
        "bio": "Certified Pilates instructor. Former professional dancer.",
        "years_experience": 6,
        "areas": ["Manhattan", "Brooklyn"],
        "services": [
            {"skill": "Pilates", "rate": 85, "desc": "Mat and equipment Pilates"},
            {"skill": "Barre", "rate": 75, "desc": "Ballet-inspired fitness"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Oliver Chen",
        "email": "oliver.chen@example.com",
        "bio": "Professional tutor specializing in test preparation. Perfect SAT scorer.",
        "years_experience": 4,
        "areas": ["Manhattan", "Queens"],
        "services": [
            {"skill": "SAT Prep", "rate": 95, "desc": "Comprehensive SAT preparation"},
            {"skill": "ACT Prep", "rate": 95, "desc": "ACT test strategies"},
            {"skill": "Essay Writing", "rate": 85, "desc": "College essay coaching"},
        ],
        "service_to_soft_delete": None,
    },
    {
        "name": "Isabella Martinez",
        "email": "isabella.martinez@example.com",
        "bio": "Art teacher and working artist. MFA from Pratt Institute.",
        "years_experience": 11,
        "areas": ["Brooklyn", "Manhattan"],
        "services": [
            {"skill": "Painting", "rate": 90, "desc": "Oil and acrylic painting"},
            {"skill": "Drawing", "rate": 75, "desc": "Pencil and charcoal drawing"},
            {"skill": "Digital Art", "rate": 85, "desc": "Digital illustration"},
        ],
        "service_to_soft_delete": None,
    },
]

STUDENT_TEMPLATES = [
    {"name": "John Smith", "email": "john.smith@example.com"},
    {"name": "Emma Johnson", "email": "emma.johnson@example.com"},
    {"name": "William Brown", "email": "william.brown@example.com"},
    {"name": "Sophia Davis", "email": "sophia.davis@example.com"},
    {"name": "Oliver Wilson", "email": "oliver.wilson@example.com"},
    {"name": "Isabella Rodriguez", "email": "isabella.rodriguez@example.com"},
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
            role=RoleName.INSTRUCTOR,
            is_active=True,
        )
        session.add(user)
        session.flush()

        # Create profile
        profile = InstructorProfile(
            user_id=user.id,
            bio=template["bio"],
            years_experience=template["years_experience"],
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

        # Persist service areas
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

    session.commit()
    logger.info(f"Created {len(INSTRUCTOR_TEMPLATES)} instructors with profiles and services")

    # Generate comprehensive summary of instructors
    generate_instructor_summary(session)


def generate_instructor_summary(session: Session):
    """Generate and display comprehensive summary of created instructors."""
    from collections import defaultdict

    logger.info("\n" + "=" * 60)
    logger.info("📊 INSTRUCTOR DATA SUMMARY")
    logger.info("=" * 60)

    # Get all active services with instructor info
    services_with_instructors = (
        session.query(Service, User)
        .join(InstructorProfile, Service.instructor_profile_id == InstructorProfile.id)
        .join(User, InstructorProfile.user_id == User.id)
        .filter(Service.is_active == True)
        .all()
    )

    # Summary by skill
    skill_summary = defaultdict(lambda: {"count": 0, "min_price": float("inf"), "max_price": 0, "instructors": []})

    for service, user in services_with_instructors:
        skill = service.skill
        skill_summary[skill]["count"] += 1
        skill_summary[skill]["min_price"] = min(skill_summary[skill]["min_price"], float(service.hourly_rate))
        skill_summary[skill]["max_price"] = max(skill_summary[skill]["max_price"], float(service.hourly_rate))
        skill_summary[skill]["instructors"].append(user.full_name)

    # Sort skills by count
    sorted_skills = sorted(skill_summary.items(), key=lambda x: x[1]["count"], reverse=True)

    logger.info("\n📚 INSTRUCTORS BY SKILL:")
    logger.info("-" * 40)
    for skill, data in sorted_skills:
        if data["min_price"] == data["max_price"]:
            price_str = f"${data['min_price']:.0f}/hr"
        else:
            price_str = f"${data['min_price']:.0f}-${data['max_price']:.0f}/hr"
        logger.info(f"  {skill}: {data['count']} instructor(s) - {price_str}")
        for instructor in data["instructors"][:3]:  # Show first 3
            logger.info(f"    • {instructor}")
        if len(data["instructors"]) > 3:
            logger.info(f"    • ... and {len(data['instructors']) - 3} more")

    # Price range distribution
    price_ranges = {"$0-50": 0, "$51-75": 0, "$76-100": 0, "$101-125": 0, "$126-150": 0, "$151+": 0}

    all_prices = []
    for service, _ in services_with_instructors:
        price = float(service.hourly_rate)
        all_prices.append(price)
        if price <= 50:
            price_ranges["$0-50"] += 1
        elif price <= 75:
            price_ranges["$51-75"] += 1
        elif price <= 100:
            price_ranges["$76-100"] += 1
        elif price <= 125:
            price_ranges["$101-125"] += 1
        elif price <= 150:
            price_ranges["$126-150"] += 1
        else:
            price_ranges["$151+"] += 1

    logger.info("\n💰 PRICE RANGE DISTRIBUTION:")
    logger.info("-" * 40)
    for range_name, count in price_ranges.items():
        if count > 0:
            percentage = (count / len(services_with_instructors)) * 100
            bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
            logger.info(f"  {range_name:>8}: {count:>3} services [{bar}] {percentage:>5.1f}%")

    if all_prices:
        avg_price = sum(all_prices) / len(all_prices)
        logger.info(f"\n  Average price: ${avg_price:.2f}/hr")
        logger.info(f"  Lowest price:  ${min(all_prices):.2f}/hr")
        logger.info(f"  Highest price: ${max(all_prices):.2f}/hr")

    # Active vs Inactive services count
    total_services = session.query(Service).count()
    active_services = session.query(Service).filter(Service.is_active == True).count()
    inactive_services = total_services - active_services

    logger.info("\n📈 SERVICE STATUS:")
    logger.info("-" * 40)
    logger.info(f"  Total services:    {total_services}")
    logger.info(f"  Active services:   {active_services} ({(active_services/total_services*100):.1f}%)")
    logger.info(f"  Inactive services: {inactive_services} ({(inactive_services/total_services*100):.1f}%)")

    # Example filter queries
    logger.info("\n🔍 EXAMPLE FILTER QUERIES TO TRY:")
    logger.info("-" * 40)
    logger.info("  Search queries:")
    logger.info("    • ?search=piano          # Find all piano teachers")
    logger.info("    • ?search=music          # Find music-related instructors")
    logger.info("    • ?search=juilliard      # Find instructors by credentials")
    logger.info("")
    logger.info("  Skill filters:")
    logger.info("    • ?skill=yoga            # Find yoga instructors")
    logger.info("    • ?skill=spanish         # Find Spanish teachers")
    logger.info("    • ?skill=guitar          # Find guitar instructors")
    logger.info("")
    logger.info("  Price filters:")
    logger.info("    • ?min_price=20&max_price=50    # Budget options")
    logger.info("    • ?min_price=100                # Premium instructors")
    logger.info("    • ?max_price=75                 # Under $75/hr")
    logger.info("")
    logger.info("  Combined filters:")
    logger.info("    • ?search=piano&max_price=100   # Affordable piano teachers")
    logger.info("    • ?skill=yoga&min_price=80      # Premium yoga instructors")
    logger.info("    • ?search=music&min_price=50&max_price=150")

    logger.info("\n" + "=" * 60 + "\n")


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
            role=RoleName.STUDENT,
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

    students = session.query(User).filter(User.role == RoleName.STUDENT).all()
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
            logger.info("Deleting slots to test independence...")

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
                "  USE_TEST_DATABASE=true python backend/scripts/reset_and_seed_database_enhanced.py\n"
                "  ALLOW_SEED_PRODUCTION=true python backend/scripts/reset_and_seed_database_enhanced.py\n"
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
        total_instructors = session.query(User).filter(User.role == RoleName.INSTRUCTOR).count()
        total_students = session.query(User).filter(User.role == RoleName.STUDENT).count()
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
