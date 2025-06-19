#!/usr/bin/env python3
# backend/scripts/reset_and_seed_database_enhanced.py
"""
Enhanced Database reset and seed script with profiling capabilities.

Features:
- Creates a dedicated profiling user with extensive data
- Generates realistic workload patterns
- Adds query performance logging
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

# Enhanced logging with query profiling
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('db_operations.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Query profiler
class QueryProfiler:
    def __init__(self):
        self.queries = []
        self.slow_queries = []
        self.query_threshold_ms = 100  # Log queries over 100ms
    
    def log_query(self, query: str, duration_ms: float, params: Any = None):
        query_info = {
            'query': query,
            'duration_ms': duration_ms,
            'params': params,
            'timestamp': datetime.now()
        }
        self.queries.append(query_info)
        
        if duration_ms > self.query_threshold_ms:
            self.slow_queries.append(query_info)
            logger.warning(f"SLOW QUERY ({duration_ms:.2f}ms): {query[:100]}...")
    
    def get_stats(self) -> Dict[str, Any]:
        if not self.queries:
            return {'total_queries': 0}
        
        durations = [q['duration_ms'] for q in self.queries]
        return {
            'total_queries': len(self.queries),
            'slow_queries': len(self.slow_queries),
            'avg_duration_ms': sum(durations) / len(durations),
            'max_duration_ms': max(durations),
            'min_duration_ms': min(durations),
            'total_time_ms': sum(durations)
        }

profiler = QueryProfiler()

# Set up query logging
@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(datetime.now())

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_times = conn.info.get('query_start_time', [])
    if start_times:
        start_time = start_times.pop()
        duration = (datetime.now() - start_time).total_seconds() * 1000
        profiler.log_query(statement, duration, parameters)

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
    "Manhattan - SoHo",
    "Manhattan - Financial District",
    "Brooklyn - Williamsburg",
    "Brooklyn - Park Slope",
    "Brooklyn - DUMBO",
    "Queens - Astoria",
    "Queens - Long Island City",
]

# Profiling user - instructor with MASSIVE data
PROFILING_USER = {
    "name": "Performance Test Instructor",
    "email": "profiling@instainstru.com",
    "bio": "Test instructor for database performance profiling with extensive availability and booking history",
    "years_experience": 10,
    "areas": NYC_AREAS,  # All areas for maximum data
    "services": [
        {"skill": "Performance Testing", "rate": 100, "desc": "Database query optimization"},
        {"skill": "Load Testing", "rate": 150, "desc": "System stress testing"},
        {"skill": "Query Profiling", "rate": 200, "desc": "SQL performance analysis"}
    ]
}

def cleanup_database(session: Session) -> List[int]:
    """Enhanced cleanup with timing."""
    logger.info("Starting database cleanup...")
    start_time = datetime.now()
    
    # Get users to exclude
    excluded_users = session.query(User).filter(
        User.email.in_(EXCLUDE_FROM_CLEANUP)
    ).all()
    
    excluded_ids = [user.id for user in excluded_users]
    logger.info(f"Preserving {len(excluded_ids)} users")
    
    # Batch delete operations for better performance
    users_to_delete = session.query(User.id).filter(
        ~User.id.in_(excluded_ids)
    ).all()
    users_to_delete_ids = [u[0] for u in users_to_delete]
    
    if users_to_delete_ids:
        # Use bulk operations where possible
        deleted_counts = {}
        
        # Clear slot references
        deleted_counts['slot_refs'] = session.query(AvailabilitySlot).filter(
            AvailabilitySlot.booking_id.isnot(None)
        ).update({"booking_id": None}, synchronize_session=False)
        
        # Delete bookings
        deleted_counts['bookings'] = session.query(Booking).filter(
            or_(
                Booking.student_id.in_(users_to_delete_ids),
                Booking.instructor_id.in_(users_to_delete_ids)
            )
        ).delete(synchronize_session=False)
        
        # Delete availability data
        avail_subquery = session.query(InstructorAvailability.id).filter(
            InstructorAvailability.instructor_id.in_(users_to_delete_ids)
        ).subquery()
        
        deleted_counts['slots'] = session.query(AvailabilitySlot).filter(
            AvailabilitySlot.availability_id.in_(avail_subquery)
        ).delete(synchronize_session=False)
        
        deleted_counts['availability'] = session.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # Delete other related data
        deleted_counts['blackouts'] = session.query(BlackoutDate).filter(
            BlackoutDate.instructor_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # Delete services and profiles
        profile_subquery = session.query(InstructorProfile.id).filter(
            InstructorProfile.user_id.in_(users_to_delete_ids)
        ).subquery()
        
        deleted_counts['services'] = session.query(Service).filter(
            Service.instructor_profile_id.in_(profile_subquery)
        ).delete(synchronize_session=False)
        
        deleted_counts['profiles'] = session.query(InstructorProfile).filter(
            InstructorProfile.user_id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        # Delete users
        deleted_counts['users'] = session.query(User).filter(
            User.id.in_(users_to_delete_ids)
        ).delete(synchronize_session=False)
        
        session.commit()
        
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Cleanup complete in {duration:.2f}s:")
        for entity, count in deleted_counts.items():
            logger.info(f"  - {entity}: {count}")
    
    return excluded_ids

def create_profiling_instructor(session: Session) -> User:
    """Create a special instructor with extensive data for profiling."""
    logger.info("Creating profiling instructor...")
    
    # Check if already exists
    existing = session.query(User).filter(User.email == PROFILING_USER["email"]).first()
    if existing:
        logger.info("Profiling user already exists")
        return existing
    
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
    
    # Create EXTENSIVE availability (365 days, multiple slots per day)
    logger.info("Creating extensive availability for profiling...")
    today = date.today()
    slots_created = 0
    
    # Use bulk insert for better performance
    availability_entries = []
    slot_entries = []
    
    for day_offset in range(365):  # Full year
        current_date = today + timedelta(days=day_offset)
        
        # Skip some days randomly (10% chance)
        if random.random() < 0.1:
            continue
        
        # Create availability entry
        availability_entries.append({
            'instructor_id': user.id,
            'date': current_date,
            'is_cleared': False
        })
    
    # Bulk insert availability
    if availability_entries:
        # Use bulk_insert_mappings and then query back
        session.bulk_insert_mappings(InstructorAvailability, availability_entries)
        session.flush()
        
        # Query back the created entries
        created_availabilities = session.query(
            InstructorAvailability.id,
            InstructorAvailability.date
        ).filter(
            InstructorAvailability.instructor_id == user.id,
            InstructorAvailability.date >= today
        ).all()
        
        # Create slots for each availability
        for avail_id, avail_date in created_availabilities:
            # Random number of slots (1-6 per day)
            num_slots = random.randint(1, 6)
            start_hour = 8
            
            for _ in range(num_slots):
                duration = random.choice([1, 1.5, 2])
                if start_hour + duration <= 20:
                    slot_entries.append({
                        'availability_id': avail_id,
                        'start_time': time(int(start_hour), int((start_hour % 1) * 60)),
                        'end_time': time(int(start_hour + duration), int(((start_hour + duration) % 1) * 60))
                    })
                    start_hour += duration + random.uniform(0.5, 2)
                    slots_created += 1
        
        # Bulk insert slots
        if slot_entries:
            session.bulk_insert_mappings(AvailabilitySlot, slot_entries)
            session.flush()
    
    session.commit()
    logger.info(f"Created profiling instructor with {len(availability_entries)} days and {slots_created} slots")
    
    return user

def create_test_bookings_for_profiling(session: Session, instructor: User, count: int = 1000):
    """Create many bookings for the profiling instructor."""
    logger.info(f"Creating {count} test bookings for profiling...")
    
    # Get all students
    students = session.query(User).filter(User.role == UserRole.STUDENT).all()
    if not students:
        logger.warning("No students found, skipping bookings")
        return
    
    # Get instructor's service
    service = session.query(Service).join(InstructorProfile).filter(
        InstructorProfile.user_id == instructor.id
    ).first()
    
    if not service:
        logger.warning("No service found for profiling instructor")
        return
    
    # Get available slots
    available_slots = session.query(AvailabilitySlot).join(InstructorAvailability).filter(
        InstructorAvailability.instructor_id == instructor.id,
        AvailabilitySlot.booking_id.is_(None),
        InstructorAvailability.date >= date.today()
    ).limit(count).all()
    
    bookings_created = 0
    booking_entries = []
    
    for slot in available_slots[:count]:
        student = random.choice(students)
        
        # Calculate booking details
        duration_minutes = 60
        total_price = float(service.hourly_rate)
        
        booking_entries.append({
            'student_id': student.id,
            'instructor_id': instructor.id,
            'service_id': service.id,
            'availability_slot_id': slot.id,
            'booking_date': slot.availability.date,
            'start_time': slot.start_time,
            'end_time': slot.end_time,
            'service_name': service.skill,
            'hourly_rate': service.hourly_rate,
            'total_price': Decimal(str(total_price)),
            'duration_minutes': duration_minutes,
            'status': BookingStatus.CONFIRMED,
            'location_type': random.choice(['student_home', 'instructor_location', 'neutral']),
            'meeting_location': f"Test location {bookings_created}",
            'created_at': datetime.now(),
            'confirmed_at': datetime.now()
        })
        bookings_created += 1
    
    # Bulk insert bookings
    if booking_entries:
        # Insert bookings
        session.bulk_insert_mappings(Booking, booking_entries)
        
        # Update slots to mark as booked
        slot_ids = [slot.id for slot in available_slots[:count]]
        session.query(AvailabilitySlot).filter(
            AvailabilitySlot.id.in_(slot_ids)
        ).update(
            {AvailabilitySlot.booking_id: Booking.id},
            synchronize_session=False
        )
    
    session.commit()
    logger.info(f"Created {bookings_created} test bookings")

def analyze_indexes(session: Session):
    """Analyze current database indexes."""
    logger.info("\nAnalyzing database indexes...")
    
    # Get all indexes
    result = session.execute(text("""
        SELECT 
            schemaname,
            tablename,
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    """))
    
    indexes_by_table = {}
    for row in result:
        table = row[1]
        if table not in indexes_by_table:
            indexes_by_table[table] = []
        indexes_by_table[table].append({
            'name': row[2],
            'definition': row[3]
        })
    
    # Check for missing indexes based on foreign keys
    missing_indexes = []
    fk_query = text("""
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
    """)
    
    fk_result = session.execute(fk_query)
    for row in fk_result:
        table_name = row[0]
        column_name = row[1]
        
        # Check if index exists for this FK
        has_index = False
        if table_name in indexes_by_table:
            for idx in indexes_by_table[table_name]:
                if column_name in idx['definition']:
                    has_index = True
                    break
        
        if not has_index:
            missing_indexes.append(f"{table_name}.{column_name}")
    
    # Report findings
    logger.info(f"\nIndex Analysis:")
    logger.info(f"Total tables: {len(indexes_by_table)}")
    logger.info(f"Total indexes: {sum(len(idxs) for idxs in indexes_by_table.values())}")
    
    if missing_indexes:
        logger.warning(f"\nMissing indexes on foreign keys:")
        for missing in missing_indexes:
            logger.warning(f"  - {missing}")
    
    # Check for duplicate indexes
    logger.info("\nChecking for duplicate indexes...")
    result = session.execute(text("""
        SELECT 
            indrelid::regclass AS table_name,
            array_agg(indexrelid::regclass) AS duplicate_indexes
        FROM pg_index
        GROUP BY indrelid, indkey
        HAVING COUNT(*) > 1
    """))
    
    duplicates = list(result)
    if duplicates:
        logger.warning("Found duplicate indexes:")
        for dup in duplicates:
            logger.warning(f"  - Table: {dup[0]}, Indexes: {dup[1]}")

def main():
    """Enhanced main function with profiling."""
    logger.info("Starting enhanced database reset and seed process...")
    
    # Create engine with echo for SQL logging
    engine = create_engine(
        settings.database_url,
        echo=False,  # Set to True for SQL output
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
    session = Session(engine)
    
    try:
        # Step 1: Cleanup with profiling
        excluded_ids = cleanup_database(session)
        
        # Step 2: Create instructors (existing code)
        from scripts.reset_and_seed_database import (
            create_dummy_instructors, 
            create_dummy_students,
            create_sample_bookings,
            INSTRUCTOR_TEMPLATES,
            STUDENT_TEMPLATES
        )
        create_dummy_instructors(session)
        create_dummy_students(session)
        create_sample_bookings(session)
        
        # Step 3: Create profiling user with extensive data
        profiling_user = create_profiling_instructor(session)
        create_test_bookings_for_profiling(session, profiling_user, count=500)
        
        # Step 4: Analyze indexes
        analyze_indexes(session)
        
        # Step 5: Run sample queries for profiling
        logger.info("\n" + "="*50)
        logger.info("Running sample queries for profiling...")
        
        # Test query 1: Week availability (common operation)
        start = datetime.now()
        result = session.execute(text("""
            SELECT ia.date, ast.start_time, ast.end_time, ast.booking_id
            FROM instructor_availability ia
            JOIN availability_slots ast ON ia.id = ast.availability_id
            WHERE ia.instructor_id = :instructor_id
            AND ia.date BETWEEN :start_date AND :end_date
            ORDER BY ia.date, ast.start_time
        """), {
            'instructor_id': profiling_user.id,
            'start_date': date.today(),
            'end_date': date.today() + timedelta(days=7)
        })
        duration = (datetime.now() - start).total_seconds() * 1000
        logger.info(f"Week availability query: {duration:.2f}ms ({len(list(result))} rows)")
        
        # Test query 2: Booking conflicts check
        start = datetime.now()
        result = session.execute(text("""
            SELECT b.id, b.start_time, b.end_time, u.full_name
            FROM bookings b
            JOIN users u ON b.student_id = u.id
            WHERE b.instructor_id = :instructor_id
            AND b.booking_date = :date
            AND b.status IN ('CONFIRMED', 'COMPLETED')
            AND b.start_time < :end_time
            AND b.end_time > :start_time
        """), {
            'instructor_id': profiling_user.id,
            'date': date.today() + timedelta(days=1),
            'start_time': time(10, 0),
            'end_time': time(11, 0)
        })
        duration = (datetime.now() - start).total_seconds() * 1000
        logger.info(f"Conflict check query: {duration:.2f}ms ({len(list(result))} rows)")
        
        # Step 6: Summary with profiling stats
        total_users = session.query(User).count()
        total_instructors = session.query(User).filter(User.role == UserRole.INSTRUCTOR).count()
        total_students = session.query(User).filter(User.role == UserRole.STUDENT).count()
        total_bookings = session.query(Booking).count()
        total_slots = session.query(AvailabilitySlot).count()
        
        # Get profiling stats
        stats = profiler.get_stats()
        
        logger.info("\n" + "="*50)
        logger.info("Database reset complete!")
        logger.info(f"Total users: {total_users}")
        logger.info(f"  - Instructors: {total_instructors}")
        logger.info(f"  - Students: {total_students}")
        logger.info(f"Total bookings: {total_bookings}")
        logger.info(f"Total availability slots: {total_slots}")
        
        logger.info("\nQuery Profiling Summary:")
        logger.info(f"  - Total queries: {stats['total_queries']}")
        logger.info(f"  - Slow queries (>{profiler.query_threshold_ms}ms): {stats.get('slow_queries', 0)}")
        if stats['total_queries'] > 0:
            logger.info(f"  - Average duration: {stats['avg_duration_ms']:.2f}ms")
            logger.info(f"  - Max duration: {stats['max_duration_ms']:.2f}ms")
            logger.info(f"  - Total time: {stats['total_time_ms']:.2f}ms")
        
        logger.info("\nProfiling user credentials:")
        logger.info(f"  Email: {PROFILING_USER['email']}")
        logger.info(f"  Password: {TEST_PASSWORD}")
        logger.info("\nUse this user for performance testing!")
        
        # Save slow queries to file
        if profiler.slow_queries:
            with open('slow_queries.log', 'w') as f:
                f.write("SLOW QUERIES REPORT\n")
                f.write("="*50 + "\n\n")
                for query in profiler.slow_queries:
                    f.write(f"Duration: {query['duration_ms']:.2f}ms\n")
                    f.write(f"Time: {query['timestamp']}\n")
                    f.write(f"Query: {query['query']}\n")
                    f.write("-"*50 + "\n\n")
            logger.info(f"\nSlow queries saved to slow_queries.log")
        
    except Exception as e:
        logger.error(f"Error during database reset: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()