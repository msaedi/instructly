#!/usr/bin/env python3
# backend/scripts/reset_and_seed_database_enhanced_fixed.py
"""
FIXED Enhanced Database reset and seed script with profiling capabilities.

Features:
- Creates a dedicated profiling user with extensive data
- FIXED: Properly links bookings to slots
- Generates realistic workload patterns
- Creates varied data densities for testing
"""

import sys
import os
from datetime import datetime, date, time, timedelta
import random
from pathlib import Path
from decimal import Decimal
import logging
from typing import List, Dict, Any

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, and_, or_, event, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from app.database import Base
from app.models.user import User, UserRole
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.availability import InstructorAvailability, AvailabilitySlot, BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.password_reset import PasswordResetToken
from app.core.config import settings
from app.auth import get_password_hash

# Enhanced logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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

# Profiling user - instructor with extensive but REALISTIC data
PROFILING_USER = {
    "name": "Performance Test Instructor",
    "email": "profiling@instainstru.com",
    "bio": "Test instructor for database performance profiling with realistic availability and booking patterns",
    "years_experience": 10,
    "areas": NYC_AREAS[:3],  # Just 3 areas for more realistic data
    "services": [
        {"skill": "Performance Testing", "rate": 100, "desc": "Database query optimization"},
        {"skill": "Load Testing", "rate": 150, "desc": "System stress testing"},
    ]
}

# Student and Instructor templates (from original script)
INSTRUCTOR_TEMPLATES = [
    {
        "name": "Sarah Chen",
        "email": "sarah.chen@example.com",
        "bio": "Experienced piano and music theory instructor with 15 years of teaching experience. Specializes in classical and jazz piano for all skill levels.",
        "years_experience": 15,
        "areas": ["Manhattan - Upper East Side", "Manhattan - Upper West Side", "Manhattan - Midtown"],
        "services": [
            {"skill": "Piano", "rate": 80, "desc": "Classical and jazz piano for all levels"},
            {"skill": "Music Theory", "rate": 70, "desc": "Comprehensive music theory and composition"}
        ]
    },
    {
        "name": "Michael Rodriguez",
        "email": "michael.rodriguez@example.com",
        "bio": "Professional guitarist and guitar instructor. Expert in rock, blues, and acoustic styles. Patient approach perfect for beginners.",
        "years_experience": 10,
        "areas": ["Brooklyn - Park Slope", "Brooklyn - DUMBO", "Manhattan - Greenwich Village"],
        "services": [
            {"skill": "Guitar", "rate": 75, "desc": "Electric and acoustic guitar lessons"},
            {"skill": "Bass Guitar", "rate": 75, "desc": "Bass guitar fundamentals and advanced techniques"}
        ]
    },
    {
        "name": "Emily Watson",
        "email": "emily.watson@example.com",
        "bio": "Certified math tutor specializing in high school and college-level mathematics. SAT/ACT prep expert with proven results.",
        "years_experience": 8,
        "areas": ["Manhattan - Chelsea", "Manhattan - Greenwich Village", "Manhattan - SoHo"],
        "services": [
            {"skill": "Math Tutoring", "rate": 90, "desc": "Algebra, Calculus, and Statistics"},
            {"skill": "SAT/ACT Prep", "rate": 100, "desc": "Comprehensive test preparation"}
        ]
    },
    {
        "name": "James Kim",
        "email": "james.kim@example.com",
        "bio": "Professional software engineer offering programming lessons. Specializes in Python, JavaScript, and web development.",
        "years_experience": 12,
        "areas": ["Queens - Long Island City", "Queens - Astoria", "Manhattan - Midtown"],
        "services": [
            {"skill": "Python Programming", "rate": 95, "desc": "From basics to advanced Python development"},
            {"skill": "Web Development", "rate": 100, "desc": "HTML, CSS, JavaScript, and React"}
        ]
    },
    {
        "name": "Dr. Amanda Foster",
        "email": "amanda.foster@example.com",
        "bio": "PhD in Chemistry with 10 years of tutoring experience. Specializes in AP Chemistry and organic chemistry for pre-med students.",
        "years_experience": 10,
        "areas": ["Manhattan - Upper East Side", "Manhattan - Midtown"],
        "services": [
            {"skill": "Chemistry Tutoring", "rate": 95, "desc": "General, Organic, and AP Chemistry"},
            {"skill": "Science Test Prep", "rate": 100, "desc": "AP and standardized test preparation"}
        ]
    }
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
    excluded_users = session.query(User).filter(
        User.email.in_(EXCLUDE_FROM_CLEANUP)
    ).all()
    
    excluded_ids = [user.id for user in excluded_users]
    logger.info(f"Preserving {len(excluded_ids)} users")
    
    # Get all test users to delete
    users_to_delete = session.query(User).filter(
        ~User.id.in_(excluded_ids),
        or_(
            User.email.like('%@example.com'),
            User.email == PROFILING_USER["email"]
        )
    ).all()
    
    user_ids_to_delete = [u.id for u in users_to_delete]
    logger.info(f"Deleting {len(user_ids_to_delete)} users")
    
    if user_ids_to_delete:
        # Delete in correct order to respect foreign keys
        
        # 1. Clear slot booking references
        session.query(AvailabilitySlot).filter(
            AvailabilitySlot.booking_id.isnot(None)
        ).update({"booking_id": None}, synchronize_session=False)
        
        # 2. Delete bookings
        session.query(Booking).filter(
            or_(
                Booking.student_id.in_(user_ids_to_delete),
                Booking.instructor_id.in_(user_ids_to_delete)
            )
        ).delete(synchronize_session=False)
        
        # 3. Delete availability slots
        subquery = session.query(InstructorAvailability.id).filter(
            InstructorAvailability.instructor_id.in_(user_ids_to_delete)
        ).subquery()
        session.query(AvailabilitySlot).filter(
            AvailabilitySlot.availability_id.in_(subquery)
        ).delete(synchronize_session=False)
        
        # 4. Delete availability
        session.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id.in_(user_ids_to_delete)
        ).delete(synchronize_session=False)
        
        # 5. Delete blackout dates
        session.query(BlackoutDate).filter(
            BlackoutDate.instructor_id.in_(user_ids_to_delete)
        ).delete(synchronize_session=False)
        
        # 6. Delete services
        profile_subquery = session.query(InstructorProfile.id).filter(
            InstructorProfile.user_id.in_(user_ids_to_delete)
        ).subquery()
        session.query(Service).filter(
            Service.instructor_profile_id.in_(profile_subquery)
        ).delete(synchronize_session=False)
        
        # 7. Delete instructor profiles
        session.query(InstructorProfile).filter(
            InstructorProfile.user_id.in_(user_ids_to_delete)
        ).delete(synchronize_session=False)
        
        # 8. Delete password reset tokens
        session.query(PasswordResetToken).filter(
            PasswordResetToken.user_id.in_(user_ids_to_delete)
        ).delete(synchronize_session=False)
        
        # 9. Finally delete users
        session.query(User).filter(
            User.id.in_(user_ids_to_delete)
        ).delete(synchronize_session=False)
        
        session.commit()
    
    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Cleanup complete in {duration:.2f}s")
    
    return excluded_ids

def create_dummy_instructors(session: Session):
    """Create dummy instructors with realistic availability."""
    logger.info("Creating dummy instructors...")
    
    for template in INSTRUCTOR_TEMPLATES:
        # Create user
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=UserRole.INSTRUCTOR,
            is_active=True
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
            buffer_time_minutes=15
        )
        session.add(profile)
        session.flush()
        
        # Create services
        for svc in template["services"]:
            service = Service(
                instructor_profile_id=profile.id,
                skill=svc["skill"],
                hourly_rate=svc["rate"],
                description=svc["desc"]
            )
            session.add(service)
        
        # Create availability for next 8 weeks
        create_realistic_availability(session, user.id)
        
    session.commit()
    logger.info(f"Created {len(INSTRUCTOR_TEMPLATES)} instructors")

def create_realistic_availability(session: Session, instructor_id: int):
    """Create realistic availability patterns for an instructor."""
    today = date.today()
    
    # Different patterns for different instructors
    patterns = [
        # Morning person - 8am to 12pm
        [(8, 12)],
        # Afternoon person - 1pm to 5pm
        [(13, 17)],
        # Evening person - 5pm to 9pm
        [(17, 21)],
        # Split schedule - morning and evening
        [(9, 12), (16, 19)],
        # Full day with breaks
        [(9, 12), (13, 17), (18, 20)]
    ]
    
    pattern = random.choice(patterns)
    
    # Create availability for next 8 weeks
    for week_offset in range(8):
        week_start = today + timedelta(weeks=week_offset)
        
        # Vary availability by day of week
        for day_offset in range(7):
            current_date = week_start + timedelta(days=day_offset)
            
            # Skip past dates
            if current_date <= today:
                continue
            
            # Skip some days randomly (20% chance)
            if random.random() < 0.2:
                continue
            
            # Skip Sundays for some instructors
            if current_date.weekday() == 6 and random.random() < 0.5:
                continue
            
            # Create availability entry
            availability = InstructorAvailability(
                instructor_id=instructor_id,
                date=current_date,
                is_cleared=False
            )
            session.add(availability)
            session.flush()
            
            # Add time slots based on pattern
            for start_hour, end_hour in pattern:
                # Occasionally adjust times slightly
                if random.random() < 0.3:
                    start_hour += random.choice([-1, 0, 1])
                    end_hour += random.choice([-1, 0, 1])
                    
                # Ensure valid times
                start_hour = max(8, min(20, start_hour))
                end_hour = max(start_hour + 1, min(21, end_hour))
                
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=time(start_hour, 0),
                    end_time=time(end_hour, 0)
                )
                session.add(slot)

def create_dummy_students(session: Session):
    """Create dummy student accounts."""
    logger.info("Creating dummy students...")
    
    for template in STUDENT_TEMPLATES:
        user = User(
            email=template["email"],
            full_name=template["name"],
            hashed_password=get_password_hash(TEST_PASSWORD),
            role=UserRole.STUDENT,
            is_active=True
        )
        session.add(user)
    
    session.commit()
    logger.info(f"Created {len(STUDENT_TEMPLATES)} students")

def create_profiling_instructor(session: Session) -> User:
    """Create a special instructor with extensive but realistic data."""
    logger.info("Creating profiling instructor...")
    
    # Create user
    user = User(
        email=PROFILING_USER["email"],
        full_name=PROFILING_USER["name"],
        hashed_password=get_password_hash(TEST_PASSWORD),
        role=UserRole.INSTRUCTOR,
        is_active=True
    )
    session.add(user)
    session.flush()
    
    # Create profile
    profile = InstructorProfile(
        user_id=user.id,
        bio=PROFILING_USER["bio"],
        years_experience=PROFILING_USER["years_experience"],
        areas_of_service=", ".join(PROFILING_USER["areas"]),
        min_advance_booking_hours=0,  # No restrictions for testing
        buffer_time_minutes=0
    )
    session.add(profile)
    session.flush()
    
    # Create services
    for svc in PROFILING_USER["services"]:
        service = Service(
            instructor_profile_id=profile.id,
            skill=svc["skill"],
            hourly_rate=svc["rate"],
            description=svc["desc"]
        )
        session.add(service)
    
    session.flush()
    
    # Create extensive but realistic availability
    create_profiling_availability(session, user.id)
    
    session.commit()
    return user

def create_profiling_availability(session: Session, instructor_id: int):
    """Create extensive availability for profiling user."""
    logger.info("Creating profiling user availability...")
    
    today = date.today()
    slots_created = 0
    
    # Create availability for next 90 days (3 months)
    for day_offset in range(90):
        current_date = today + timedelta(days=day_offset)
        
        # Skip weekends occasionally
        if current_date.weekday() >= 5 and random.random() < 0.3:
            continue
        
        # Create availability entry
        availability = InstructorAvailability(
            instructor_id=instructor_id,
            date=current_date,
            is_cleared=False
        )
        session.add(availability)
        session.flush()
        
        # Create varied time slots
        if current_date.weekday() < 5:  # Weekday
            # Morning slots
            if random.random() < 0.7:
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=time(9, 0),
                    end_time=time(12, 0)
                )
                session.add(slot)
                slots_created += 1
            
            # Afternoon slots
            if random.random() < 0.8:
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=time(14, 0),
                    end_time=time(17, 0)
                )
                session.add(slot)
                slots_created += 1
            
            # Evening slots
            if random.random() < 0.5:
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=time(18, 0),
                    end_time=time(20, 0)
                )
                session.add(slot)
                slots_created += 1
        else:  # Weekend
            # Weekend morning
            if random.random() < 0.6:
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=time(10, 0),
                    end_time=time(12, 0)
                )
                session.add(slot)
                slots_created += 1
            
            # Weekend afternoon
            if random.random() < 0.4:
                slot = AvailabilitySlot(
                    availability_id=availability.id,
                    start_time=time(14, 0),
                    end_time=time(16, 0)
                )
                session.add(slot)
                slots_created += 1
    
    logger.info(f"Created {slots_created} availability slots for profiling user")

def create_sample_bookings(session: Session):
    """Create realistic sample bookings."""
    logger.info("Creating sample bookings...")
    
    # Get all students and instructors
    students = session.query(User).filter(User.role == UserRole.STUDENT).all()
    instructors = session.query(User).filter(
        User.role == UserRole.INSTRUCTOR,
        User.email != PROFILING_USER["email"]  # Handle profiling user separately
    ).all()
    
    bookings_created = 0
    
    for instructor in instructors:
        # Get instructor's services
        services = session.query(Service).join(InstructorProfile).filter(
            InstructorProfile.user_id == instructor.id
        ).all()
        
        if not services:
            continue
        
        # Get available slots for next 30 days
        future_date = date.today() + timedelta(days=30)
        available_slots = session.query(AvailabilitySlot).join(
            InstructorAvailability
        ).filter(
            InstructorAvailability.instructor_id == instructor.id,
            InstructorAvailability.date >= date.today(),
            InstructorAvailability.date <= future_date,
            AvailabilitySlot.booking_id.is_(None)
        ).all()
        
        # Book 30-50% of available slots
        slots_to_book = random.sample(
            available_slots, 
            min(len(available_slots), int(len(available_slots) * random.uniform(0.3, 0.5)))
        )
        
        for slot in slots_to_book:
            student = random.choice(students)
            service = random.choice(services)
            
            # Calculate duration
            start_datetime = datetime.combine(date.today(), slot.start_time)
            end_datetime = datetime.combine(date.today(), slot.end_time)
            duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)
            
            booking = Booking(
                student_id=student.id,
                instructor_id=instructor.id,
                service_id=service.id,
                availability_slot_id=slot.id,
                booking_date=slot.availability.date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                service_name=service.skill,
                hourly_rate=service.hourly_rate,
                total_price=Decimal(str(service.hourly_rate * duration_minutes / 60)),
                duration_minutes=duration_minutes,
                status=BookingStatus.CONFIRMED,
                location_type=random.choice(['student_home', 'instructor_location', 'neutral']),
                meeting_location=f"{random.choice(['Student home', 'Instructor studio', 'Local library'])}",
                created_at=datetime.now(),
                confirmed_at=datetime.now()
            )
            session.add(booking)
            session.flush()
            
            # FIXED: Properly update the slot's booking_id
            slot.booking_id = booking.id
            bookings_created += 1
    
    session.commit()
    logger.info(f"Created {bookings_created} bookings")

def create_profiling_bookings(session: Session, instructor: User):
    """Create bookings for profiling user - properly linked!"""
    logger.info("Creating bookings for profiling user...")
    
    students = session.query(User).filter(User.role == UserRole.STUDENT).all()
    if not students:
        logger.warning("No students found")
        return
    
    service = session.query(Service).join(InstructorProfile).filter(
        InstructorProfile.user_id == instructor.id
    ).first()
    
    if not service:
        logger.warning("No service found for profiling instructor")
        return
    
    # Get available slots for next 60 days
    future_date = date.today() + timedelta(days=60)
    available_slots = session.query(AvailabilitySlot).join(
        InstructorAvailability
    ).filter(
        InstructorAvailability.instructor_id == instructor.id,
        InstructorAvailability.date >= date.today(),
        InstructorAvailability.date <= future_date,
        AvailabilitySlot.booking_id.is_(None)
    ).limit(200).all()  # Book up to 200 slots
    
    bookings_created = 0
    
    # Book 40% of available slots
    slots_to_book = random.sample(
        available_slots,
        min(len(available_slots), int(len(available_slots) * 0.4))
    )
    
    for slot in slots_to_book:
        student = random.choice(students)
        
        # Calculate duration
        start_datetime = datetime.combine(date.today(), slot.start_time)
        end_datetime = datetime.combine(date.today(), slot.end_time)
        duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)
        
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            service_id=service.id,
            availability_slot_id=slot.id,
            booking_date=slot.availability.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal(str(service.hourly_rate * duration_minutes / 60)),
            duration_minutes=duration_minutes,
            status=BookingStatus.CONFIRMED,
            location_type='neutral',
            meeting_location="Performance Testing Location",
            created_at=datetime.now(),
            confirmed_at=datetime.now()
        )
        session.add(booking)
        session.flush()
        
        # FIXED: Properly update the slot's booking_id
        slot.booking_id = booking.id
        bookings_created += 1
    
    session.commit()
    logger.info(f"Created {bookings_created} bookings for profiling user")

def main():
    """Main function."""
    logger.info("Starting database reset and seed process...")
    
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session = Session(engine)
    
    try:
        # Step 1: Cleanup
        cleanup_database(session)
        
        # Step 2: Create regular users
        create_dummy_instructors(session)
        create_dummy_students(session)
        create_sample_bookings(session)
        
        # Step 3: Create profiling user
        profiling_user = create_profiling_instructor(session)
        create_profiling_bookings(session, profiling_user)
        
        # Step 4: Summary
        total_users = session.query(User).count()
        total_instructors = session.query(User).filter(User.role == UserRole.INSTRUCTOR).count()
        total_students = session.query(User).filter(User.role == UserRole.STUDENT).count()
        total_bookings = session.query(Booking).count()
        total_slots = session.query(AvailabilitySlot).count()
        booked_slots = session.query(AvailabilitySlot).filter(
            AvailabilitySlot.booking_id.isnot(None)
        ).count()
        
        logger.info("\n" + "="*50)
        logger.info("Database reset complete!")
        logger.info(f"Total users: {total_users}")
        logger.info(f"  - Instructors: {total_instructors}")
        logger.info(f"  - Students: {total_students}")
        logger.info(f"Total bookings: {total_bookings}")
        logger.info(f"Total availability slots: {total_slots}")
        logger.info(f"  - Booked: {booked_slots}")
        logger.info(f"  - Available: {total_slots - booked_slots}")
        
        logger.info("\nTest credentials:")
        logger.info(f"  All passwords: {TEST_PASSWORD}")
        logger.info("\nInstructors:")
        for t in INSTRUCTOR_TEMPLATES:
            logger.info(f"  - {t['email']}")
        logger.info(f"  - {PROFILING_USER['email']} (extensive data)")
        logger.info("\nStudents:")
        for t in STUDENT_TEMPLATES[:3]:
            logger.info(f"  - {t['email']}")
        
    except Exception as e:
        logger.error(f"Error during database reset: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()