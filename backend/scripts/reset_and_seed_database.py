#!/usr/bin/env python3
"""
Database reset and seed script for InstaInstru.

This script provides a consistent way to reset the database to a known state
with test data. It preserves specified users while removing all others and
creates a set of diverse instructor profiles with varied availability patterns.

Usage:
    python scripts/reset_and_seed_database.py
"""

import sys
import os
from datetime import datetime, date, time, timedelta
import random
from pathlib import Path

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import Session
from app.database import Base
from app.models.user import User, UserRole
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.availability import InstructorAvailability, AvailabilitySlot, BlackoutDate
from app.models.password_reset import PasswordResetToken
from app.core.config import settings
from app.auth import get_password_hash
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
EXCLUDE_FROM_CLEANUP = [
    "mehdisaedi@hotmail.com",  # Keep this user
    # Add more emails here as needed
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

# Instructor templates
INSTRUCTOR_TEMPLATES = [
    {
        "name": "Sarah Chen",
        "email": "sarah.chen@example.com",
        "bio": "Certified yoga instructor with 8 years of experience in Vinyasa and Hatha yoga. I believe in creating a peaceful, inclusive environment where students of all levels can explore their practice. Specialized in stress relief and flexibility training.",
        "years_experience": 8,
        "areas": ["Manhattan - Upper East Side", "Manhattan - Midtown"],
        "services": [
            {"skill": "Yoga", "rate": 85, "desc": "Vinyasa and Hatha yoga for all levels"},
            {"skill": "Meditation", "rate": 65, "desc": "Guided meditation and mindfulness techniques"},
            {"skill": "Breathwork", "rate": 70, "desc": "Pranayama and breathing exercises"}
        ],
        "availability_pattern": "mornings"  # Primarily morning classes
    },
    {
        "name": "Michael Rodriguez",
        "email": "michael.rodriguez@example.com",
        "bio": "Professional pianist and music educator with a Master's from Juilliard. I specialize in classical piano but also teach jazz and contemporary styles. My approach focuses on technique, music theory, and creative expression.",
        "years_experience": 12,
        "areas": ["Manhattan - Upper West Side", "Manhattan - Greenwich Village"],
        "services": [
            {"skill": "Piano", "rate": 120, "desc": "Classical, jazz, and contemporary piano"},
            {"skill": "Music Theory", "rate": 95, "desc": "Comprehensive music theory and composition"},
            {"skill": "Sight Reading", "rate": 90, "desc": "Improve your sight reading skills"}
        ],
        "availability_pattern": "evenings"  # Evening lessons after work/school
    },
    {
        "name": "Emily Watson",
        "email": "emily.watson@example.com",
        "bio": "Native Spanish speaker with teaching certification from Instituto Cervantes. I make language learning fun and practical, focusing on conversational skills and cultural immersion. Also fluent in English and French.",
        "years_experience": 6,
        "areas": ["Brooklyn - Park Slope", "Brooklyn - Williamsburg"],
        "services": [
            {"skill": "Spanish", "rate": 75, "desc": "Spanish for all levels - conversation to business"},
            {"skill": "ESL", "rate": 70, "desc": "English as a Second Language"},
            {"skill": "French", "rate": 80, "desc": "French language and culture"}
        ],
        "availability_pattern": "flexible"  # Various times throughout the week
    },
    {
        "name": "David Kim",
        "email": "david.kim@example.com",
        "bio": "ACE certified personal trainer specializing in strength training and HIIT. Former college athlete with expertise in sports performance and injury prevention. I create customized workout plans tailored to your goals.",
        "years_experience": 10,
        "areas": ["Manhattan - Chelsea", "Manhattan - SoHo"],
        "services": [
            {"skill": "Personal Training", "rate": 100, "desc": "1-on-1 strength and conditioning"},
            {"skill": "HIIT", "rate": 85, "desc": "High-intensity interval training sessions"},
            {"skill": "Nutrition Coaching", "rate": 75, "desc": "Personalized nutrition planning"}
        ],
        "availability_pattern": "early_bird"  # Early morning and lunch sessions
    },
    {
        "name": "Lisa Thompson",
        "email": "lisa.thompson@example.com",
        "bio": "Professional photographer with 15 years in the industry. From portraits to landscapes, I teach both technical skills and artistic vision. Experienced with DSLR, mirrorless, and film photography.",
        "years_experience": 15,
        "areas": ["Brooklyn - DUMBO", "Manhattan - SoHo"],
        "services": [
            {"skill": "Photography", "rate": 110, "desc": "Digital and film photography techniques"},
            {"skill": "Photo Editing", "rate": 85, "desc": "Lightroom and Photoshop mastery"},
            {"skill": "Portrait Photography", "rate": 120, "desc": "Professional portrait techniques"}
        ],
        "availability_pattern": "weekends"  # Primarily weekends
    },
    {
        "name": "James Park",
        "email": "james.park@example.com",
        "bio": "Full-stack developer with 10+ years in the tech industry. I teach practical coding skills from web development to data science. Patient instructor who breaks down complex concepts into digestible lessons.",
        "years_experience": 10,
        "areas": ["Queens - Long Island City", "Manhattan - Midtown"],
        "services": [
            {"skill": "Web Development", "rate": 130, "desc": "HTML, CSS, JavaScript, React"},
            {"skill": "Python Programming", "rate": 125, "desc": "Python for beginners to advanced"},
            {"skill": "Data Science", "rate": 140, "desc": "Data analysis with Python and SQL"}
        ],
        "availability_pattern": "evenings_weekends"  # After work and weekends
    },
    {
        "name": "Maria Garcia",
        "email": "maria.garcia@example.com",
        "bio": "Professional chef with experience in Michelin-starred restaurants. I teach cooking techniques from basic knife skills to advanced culinary arts. Specializing in Mediterranean and Latin American cuisine.",
        "years_experience": 18,
        "areas": ["Queens - Astoria", "Manhattan - Upper West Side"],
        "services": [
            {"skill": "Cooking", "rate": 95, "desc": "From basics to gourmet techniques"},
            {"skill": "Baking", "rate": 90, "desc": "Breads, pastries, and desserts"},
            {"skill": "Meal Prep", "rate": 80, "desc": "Efficient and healthy meal preparation"}
        ],
        "availability_pattern": "variable"  # Changes week to week
    },
    {
        "name": "Robert Chang",
        "email": "robert.chang@example.com",
        "bio": "CFA charterholder with 20 years on Wall Street. I demystify finance and investing for individuals looking to take control of their financial future. From budgeting basics to advanced investment strategies.",
        "years_experience": 20,
        "areas": ["Manhattan - Financial District", "Manhattan - Midtown"],
        "services": [
            {"skill": "Financial Planning", "rate": 150, "desc": "Personal finance and budgeting"},
            {"skill": "Investment Strategy", "rate": 175, "desc": "Portfolio management and analysis"},
            {"skill": "Day Trading", "rate": 200, "desc": "Technical analysis and trading strategies"}
        ],
        "availability_pattern": "business_hours"  # Standard business hours
    },
    {
        "name": "Amanda Foster",
        "email": "amanda.foster@example.com",
        "bio": "Licensed esthetician and makeup artist for TV and film. I teach both everyday makeup techniques and special effects. Passionate about helping people feel confident and beautiful in their own skin.",
        "years_experience": 9,
        "areas": ["Manhattan - Chelsea", "Brooklyn - Williamsburg"],
        "services": [
            {"skill": "Makeup Artistry", "rate": 90, "desc": "From natural looks to glam"},
            {"skill": "Skincare", "rate": 85, "desc": "Personalized skincare routines"},
            {"skill": "Special Effects", "rate": 110, "desc": "SFX makeup for film and events"}
        ],
        "availability_pattern": "afternoons"  # Afternoon appointments
    },
    {
        "name": "Kevin Liu",
        "email": "kevin.liu@example.com",
        "bio": "Native Mandarin speaker with a PhD in Chinese Literature. I combine language instruction with cultural education, using immersive techniques to accelerate learning. Also teach Chinese calligraphy and history.",
        "years_experience": 7,
        "areas": ["Manhattan - Chinatown", "Queens - Flushing"],
        "services": [
            {"skill": "Mandarin Chinese", "rate": 85, "desc": "All levels - pinyin to business Chinese"},
            {"skill": "Calligraphy", "rate": 70, "desc": "Traditional Chinese calligraphy"},
            {"skill": "Chinese Culture", "rate": 65, "desc": "History, customs, and traditions"}
        ],
        "availability_pattern": "mixed"  # Mix of different times
    }
]

def cleanup_database(session: Session):
    """Remove all users except those in the exclude list."""
    logger.info("Starting database cleanup...")
    
    # Get users to exclude
    excluded_users = session.query(User).filter(
        User.email.in_(EXCLUDE_FROM_CLEANUP)
    ).all()
    
    excluded_ids = [user.id for user in excluded_users]
    logger.info(f"Preserving {len(excluded_ids)} users: {[u.email for u in excluded_users]}")
    
    # First, delete related data for users we're going to remove
    users_to_delete = session.query(User).filter(
        ~User.id.in_(excluded_ids)
    ).all()
    
    users_to_delete_ids = [user.id for user in users_to_delete]
    
    if users_to_delete_ids:
        # Delete in order to respect foreign key constraints
        
        # 1. First get all instructor availability IDs for users to delete
        availability_ids = session.query(InstructorAvailability.id).filter(
            InstructorAvailability.instructor_id.in_(users_to_delete_ids)
        ).all()
        availability_ids = [a[0] for a in availability_ids]
        
        # 2. Delete availability slots
        if availability_ids:
            slot_count = session.query(AvailabilitySlot).filter(
                AvailabilitySlot.availability_id.in_(availability_ids)
            ).delete(synchronize_session=False)
        else:
            slot_count = 0
        
        # 3. Delete instructor availability
        avail_count = session.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # 4. Delete blackout dates
        blackout_count = session.query(BlackoutDate).filter(
            BlackoutDate.instructor_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # 5. Get instructor profile IDs for users to delete
        profile_ids = session.query(InstructorProfile.id).filter(
            InstructorProfile.user_id.in_(users_to_delete_ids)
        ).all()
        profile_ids = [p[0] for p in profile_ids]
        
        # 6. Delete services
        if profile_ids:
            service_count = session.query(Service).filter(
                Service.instructor_profile_id.in_(profile_ids)
            ).delete(synchronize_session=False)
        else:
            service_count = 0
        
        # 7. Delete instructor profiles
        profile_count = session.query(InstructorProfile).filter(
            InstructorProfile.user_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # 8. Delete password reset tokens
        token_count = session.query(PasswordResetToken).filter(
            PasswordResetToken.user_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # 9. Finally, delete the users
        user_count = session.query(User).filter(
            User.id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        session.commit()
        
        logger.info(f"Cleanup complete:")
        logger.info(f"  - Deleted {user_count} users")
        logger.info(f"  - Deleted {profile_count} instructor profiles")
        logger.info(f"  - Deleted {service_count} services")
        logger.info(f"  - Deleted {avail_count} availability entries")
        logger.info(f"  - Deleted {slot_count} availability slots")
        logger.info(f"  - Deleted {blackout_count} blackout dates")
        logger.info(f"  - Deleted {token_count} password reset tokens")
    else:
        logger.info("No users to delete")
    
    return excluded_ids

def create_availability_pattern(session: Session, instructor_id: int, pattern: str, weeks_ahead: int = 12):
    """Create availability based on pattern type."""
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    
    patterns = {
        "mornings": {
            "days": [0, 1, 2, 3, 4, 5, 6],  # All days
            "slots": [(time(8, 0), time(12, 0))]
        },
        "evenings": {
            "days": [0, 1, 2, 3, 4],  # Weekdays
            "slots": [(time(17, 0), time(21, 0))]
        },
        "early_bird": {
            "days": [0, 1, 2, 3, 4],  # Weekdays
            "slots": [(time(6, 0), time(9, 0)), (time(12, 0), time(13, 0))]  # Early morning + lunch
        },
        "weekends": {
            "days": [5, 6],  # Saturday, Sunday
            "slots": [(time(9, 0), time(17, 0))]
        },
        "business_hours": {
            "days": [0, 1, 2, 3, 4],  # Weekdays
            "slots": [(time(9, 0), time(17, 0))]
        },
        "afternoons": {
            "days": [0, 1, 2, 3, 4, 5],  # Mon-Sat
            "slots": [(time(13, 0), time(18, 0))]
        },
        "evenings_weekends": {
            "days": [0, 1, 2, 3, 4],  # Weekday evenings
            "slots": [(time(18, 0), time(21, 0))],
            "weekend_slots": [(time(10, 0), time(16, 0))]  # Weekend days
        },
        "flexible": {
            "random": True  # Will generate random availability
        },
        "variable": {
            "random": True,
            "sparse": True  # Less dense random availability
        },
        "mixed": {
            "random": True,
            "mixed": True  # Mix of patterns
        }
    }
    
    pattern_config = patterns.get(pattern, patterns["flexible"])
    
    for week_offset in range(weeks_ahead):
        week_start = current_monday + timedelta(weeks=week_offset)
        
        # Add some randomness - occasionally skip weeks or modify pattern
        if random.random() < 0.1:  # 10% chance to skip a week (vacation, etc.)
            # Create a blackout for one random day
            blackout_day = week_start + timedelta(days=random.randint(0, 6))
            if blackout_day > today:
                blackout = BlackoutDate(
                    instructor_id=instructor_id,
                    date=blackout_day,
                    reason="Personal day"
                )
                session.add(blackout)
            continue
        
        if pattern_config.get("random"):
            # Generate random availability
            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                
                if current_date <= today:
                    continue
                
                # Random chance of being available
                if pattern_config.get("sparse") and random.random() < 0.6:
                    continue
                elif not pattern_config.get("sparse") and random.random() < 0.3:
                    continue
                
                # Create availability entry
                availability = InstructorAvailability(
                    instructor_id=instructor_id,
                    date=current_date,
                    is_cleared=False
                )
                session.add(availability)
                session.flush()
                
                # Add random time slots
                if pattern_config.get("mixed"):
                    # Mix of different slot types
                    slot_type = random.choice(["morning", "afternoon", "evening"])
                    if slot_type == "morning":
                        slots = [(time(random.randint(7, 9), 0), time(random.randint(10, 12), 0))]
                    elif slot_type == "afternoon":
                        slots = [(time(random.randint(12, 14), 0), time(random.randint(15, 17), 0))]
                    else:
                        slots = [(time(random.randint(17, 19), 0), time(random.randint(20, 21), 0))]
                else:
                    # Random slots throughout the day
                    num_slots = random.randint(1, 3)
                    slots = []
                    start_hour = 8
                    for _ in range(num_slots):
                        duration = random.choice([1, 2, 3])
                        if start_hour + duration <= 20:
                            slots.append((time(start_hour, 0), time(start_hour + duration, 0)))
                            start_hour += duration + random.randint(1, 2)
                
                for start_time, end_time in slots:
                    slot = AvailabilitySlot(
                        availability_id=availability.id,
                        start_time=start_time,
                        end_time=end_time
                    )
                    session.add(slot)
        else:
            # Use defined pattern
            days = pattern_config["days"]
            slots = pattern_config["slots"]
            
            for day_offset in days:
                current_date = week_start + timedelta(days=day_offset)
                
                if current_date <= today:
                    continue
                
                # Add slight randomness - 5% chance to skip
                if random.random() < 0.05:
                    continue
                
                availability = InstructorAvailability(
                    instructor_id=instructor_id,
                    date=current_date,
                    is_cleared=False
                )
                session.add(availability)
                session.flush()
                
                # Handle weekend slots for evenings_weekends pattern
                if pattern == "evenings_weekends" and day_offset in [5, 6]:
                    slot_list = pattern_config.get("weekend_slots", slots)
                else:
                    slot_list = slots
                
                for start_time, end_time in slot_list:
                    slot = AvailabilitySlot(
                        availability_id=availability.id,
                        start_time=start_time,
                        end_time=end_time
                    )
                    session.add(slot)
    
    session.commit()

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
            role=UserRole.INSTRUCTOR,
            is_active=True
        )
        session.add(user)
        session.flush()
        
        # Create instructor profile
        profile = InstructorProfile(
            user_id=user.id,
            bio=template["bio"],
            years_experience=template["years_experience"],
            areas_of_service=", ".join(template["areas"])  # Back to comma-separated string after migration
        )
        session.add(profile)
        session.flush()
        
        # Create services
        for svc in template["services"]:
            service = Service(
                instructor_profile_id=profile.id,
                skill=svc["skill"],
                hourly_rate=svc["rate"],
                description=svc["desc"],
                duration_override=random.choice([None, 45, 60, 90])  # Random duration
            )
            session.add(service)
        
        # Create availability pattern
        create_availability_pattern(session, user.id, template["availability_pattern"])
        
        created_count += 1
        logger.info(f"Created instructor: {template['name']} ({template['email']})")
    
    session.commit()
    logger.info(f"Created {created_count} dummy instructors")
    
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
        
        # Step 3: Summary
        total_users = session.query(User).count()
        total_instructors = session.query(User).filter(User.role == UserRole.INSTRUCTOR).count()
        total_students = session.query(User).filter(User.role == UserRole.STUDENT).count()
        
        logger.info("\n" + "="*50)
        logger.info("Database reset complete!")
        logger.info(f"Total users: {total_users}")
        logger.info(f"Instructors: {total_instructors}")
        logger.info(f"Students: {total_students}")
        logger.info(f"Preserved users: {len(excluded_ids)}")
        logger.info("="*50)
        
        logger.info("\nTest credentials for dummy accounts:")
        logger.info(f"Password for all test accounts: {TEST_PASSWORD}")
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