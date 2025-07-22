#!/usr/bin/env python3
"""
Reset and seed database using YAML configuration files.
Usage: USE_TEST_DATABASE=true python backend/scripts/reset_and_seed_yaml.py
"""

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import random
from datetime import date, datetime, time, timedelta

# Add the scripts directory to Python path so imports work from anywhere
sys.path.insert(0, str(Path(__file__).parent))

from seed_catalog_only import seed_catalog
from seed_yaml_loader import SeedDataLoader
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.core.config import settings
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.models.user import User, UserRole


class DatabaseSeeder:
    def __init__(self):
        # Use absolute path based on script location
        seed_data_path = Path(__file__).parent / "seed_data"
        self.loader = SeedDataLoader(seed_data_dir=str(seed_data_path))
        self.engine = self._create_engine()
        self.created_users = {}
        self.created_services = {}

    def _create_engine(self):
        db_url = settings.test_database_url if os.getenv("USE_TEST_DATABASE") == "true" else settings.database_url
        print(f"Using database: {'TEST' if os.getenv('USE_TEST_DATABASE') == 'true' else 'PRODUCTION'}")
        return create_engine(db_url)

    def reset_database(self):
        """Clean test data from database"""
        with Session(self.engine) as session:
            # Delete in order to respect foreign key constraints
            session.execute(
                text("DELETE FROM bookings WHERE student_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')")
            )
            session.execute(
                text(
                    "DELETE FROM bookings WHERE instructor_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')"
                )
            )
            session.execute(
                text(
                    "DELETE FROM availability_slots WHERE instructor_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')"
                )
            )
            session.execute(
                text(
                    "DELETE FROM blackout_dates WHERE instructor_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')"
                )
            )
            session.execute(
                text(
                    "DELETE FROM instructor_services WHERE instructor_profile_id IN (SELECT id FROM instructor_profiles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@example.com'))"
                )
            )
            session.execute(
                text(
                    "DELETE FROM instructor_profiles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')"
                )
            )
            session.execute(text("DELETE FROM users WHERE email LIKE '%@example.com'"))
            session.commit()
            print("✅ Cleaned test data from database")

    def seed_all(self):
        """Main seeding function"""
        print("🌱 Starting database seeding...")
        self.reset_database()

        # Seed service catalog first
        print("\n📚 Seeding service catalog...")
        db_url = self.engine.url.render_as_string(hide_password=False)
        catalog_stats = seed_catalog(db_url=db_url, verbose=True)

        self.create_students()
        self.create_instructors()
        self.create_availability()
        self.create_bookings()
        self.print_summary()
        print("✅ Database seeding complete!")

    def create_students(self):
        """Create student accounts from YAML"""
        students = self.loader.get_students()
        password = self.loader.get_default_password()

        with Session(self.engine) as session:
            for student_data in students:
                user = User(
                    email=student_data["email"],
                    full_name=student_data["full_name"],
                    role=UserRole.STUDENT,
                    hashed_password=get_password_hash(password),
                    is_active=True,
                    account_status="active",
                )
                session.add(user)
                session.flush()
                self.created_users[user.email] = user.id
                print(f"  ✅ Created student: {user.full_name}")

            session.commit()
        print(f"✅ Created {len(students)} students")

    def create_instructors(self):
        """Create instructor accounts with profiles and services from YAML"""
        instructors = self.loader.get_instructors()
        password = self.loader.get_default_password()

        with Session(self.engine) as session:
            for instructor_data in instructors:
                # Create user account
                # Allow account_status to be specified in YAML, default to "active"
                account_status = instructor_data.get("account_status", "active")
                user = User(
                    email=instructor_data["email"],
                    full_name=instructor_data["full_name"],
                    role=UserRole.INSTRUCTOR,
                    hashed_password=get_password_hash(password),
                    is_active=True,
                    account_status=account_status,
                )
                session.add(user)
                session.flush()

                # Create instructor profile
                profile_data = instructor_data.get("profile", {})
                profile = InstructorProfile(
                    user_id=user.id,
                    bio=profile_data.get("bio", ""),
                    years_experience=profile_data.get("years_experience", 1),
                    areas_of_service=", ".join(profile_data.get("areas", [])),
                    min_advance_booking_hours=2,
                    buffer_time_minutes=0,
                )
                session.add(profile)
                session.flush()

                # Create services from catalog
                service_count = 0
                # Get catalog services for mapping
                catalog_services = session.query(ServiceCatalog).all()
                service_map = {s.name: s for s in catalog_services}

                for service_data in profile_data.get("services", []):
                    service_name = service_data["name"]

                    # Find matching catalog service
                    catalog_service = service_map.get(service_name)
                    if not catalog_service:
                        print(f"  ⚠️  Service '{service_name}' not found in catalog, skipping")
                        continue

                    # Create instructor service linked to catalog
                    service = InstructorService(
                        instructor_profile_id=profile.id,
                        service_catalog_id=catalog_service.id,
                        hourly_rate=service_data["price"],
                        description=service_data.get("description"),
                        duration_options=service_data.get("duration_options", [60]),
                        is_active=True,
                    )
                    session.add(service)
                    session.flush()
                    self.created_services[f"{user.email}:{service_name}"] = service.id
                    service_count += 1

                self.created_users[user.email] = user.id
                status_info = f" [{account_status.upper()}]" if account_status != "active" else ""
                print(f"  ✅ Created instructor: {user.full_name} with {service_count} services{status_info}")

            session.commit()

        # Count instructors by status
        status_counts = {"active": 0, "suspended": 0, "deactivated": 0}
        for instructor_data in instructors:
            status = instructor_data.get("account_status", "active")
            status_counts[status] += 1

        print(f"✅ Created {len(instructors)} instructors")
        if status_counts["suspended"] > 0 or status_counts["deactivated"] > 0:
            print(
                f"   ⚠️  Including test instructors: {status_counts['suspended']} suspended, {status_counts['deactivated']} deactivated"
            )

    def create_availability(self):
        """Create availability slots based on patterns"""
        instructors = self.loader.get_instructors()
        weeks_ahead = self.loader.config.get("settings", {}).get("weeks_of_availability", 4)

        with Session(self.engine) as session:
            for instructor_data in instructors:
                pattern_name = instructor_data.get("availability_pattern")
                if not pattern_name:
                    continue

                pattern = self.loader.get_availability_pattern(pattern_name)
                if not pattern:
                    print(f"  ⚠️  Pattern '{pattern_name}' not found")
                    continue

                user_id = self.created_users.get(instructor_data["email"])
                if not user_id:
                    continue

                days_data = pattern.get("days", {})

                # Create availability for the next N weeks
                for week in range(weeks_ahead):
                    for day_name, time_slots in days_data.items():
                        # Calculate the date for this day
                        target_date = self._get_date_for_day(day_name, week)

                        for time_range in time_slots:
                            start_time = time(*[int(x) for x in time_range[0].split(":")])
                            end_time = time(*[int(x) for x in time_range[1].split(":")])

                            slot = AvailabilitySlot(
                                instructor_id=user_id,
                                specific_date=target_date,
                                start_time=start_time,
                                end_time=end_time,
                            )
                            session.add(slot)

                session.commit()
                print(f"  ✅ Created availability for {instructor_data['full_name']} using pattern '{pattern_name}'")

        print(f"✅ Created availability patterns for all instructors")

    def _get_date_for_day(self, day_name, weeks_ahead):
        """Calculate the date for a given day name and weeks ahead"""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        today = date.today()
        days_ahead = days.index(day_name.lower()) - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead + (weeks_ahead * 7))

    def _day_name_to_number(self, day_name):
        """Convert day name to number (0=Monday, 6=Sunday)"""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return days.index(day_name.lower())

    def create_bookings(self):
        """Create sample bookings for testing"""
        booking_days_ahead = self.loader.config.get("settings", {}).get("booking_days_ahead", 7)

        with Session(self.engine) as session:
            # Get all students
            students = session.query(User).filter(User.role == UserRole.STUDENT, User.email.like("%@example.com")).all()

            if not students:
                print("  ⚠️  No students found to create bookings")
                return

            booking_count = 0

            # For each instructor, create 1-3 bookings
            for instructor_email, instructor_id in self.created_users.items():
                if not instructor_email.endswith("@example.com"):
                    continue

                # Skip students
                instructor = session.query(User).filter(User.id == instructor_id).first()
                if instructor.role != UserRole.INSTRUCTOR:
                    continue

                # Get instructor's services
                services = (
                    session.query(InstructorService)
                    .join(InstructorProfile)
                    .filter(InstructorProfile.user_id == instructor_id)
                    .all()
                )

                if not services:
                    continue

                # Create 1-3 bookings for this instructor
                num_bookings = random.randint(1, min(3, len(students)))

                for _ in range(num_bookings):
                    service = random.choice(services)
                    student = random.choice(students)

                    # Pick a random duration from the service's options
                    duration = random.choice(service.duration_options)

                    # Find an available slot in the next week
                    slots = (
                        session.query(AvailabilitySlot)
                        .filter(
                            AvailabilitySlot.instructor_id == instructor_id,
                            AvailabilitySlot.specific_date >= date.today(),
                            AvailabilitySlot.specific_date <= date.today() + timedelta(days=booking_days_ahead),
                        )
                        .all()
                    )

                    if not slots:
                        continue

                    # Pick a random slot
                    slot = random.choice(slots)

                    # Calculate end time based on duration
                    start_datetime = datetime.combine(date.today(), slot.start_time)
                    end_datetime = start_datetime + timedelta(minutes=duration)

                    # Make sure booking doesn't exceed slot end time
                    if end_datetime.time() > slot.end_time:
                        continue

                    # Check if this time is already booked
                    existing = (
                        session.query(Booking)
                        .filter(
                            Booking.instructor_id == instructor_id,
                            Booking.booking_date == slot.specific_date,
                            Booking.start_time < end_datetime.time(),
                            Booking.end_time > slot.start_time,
                        )
                        .first()
                    )

                    if existing:
                        continue

                    # Get service details from catalog
                    catalog_service = session.query(ServiceCatalog).filter_by(id=service.service_catalog_id).first()

                    # Create booking
                    booking = Booking(
                        student_id=student.id,
                        instructor_id=instructor_id,
                        instructor_service_id=service.id,
                        booking_date=slot.specific_date,
                        start_time=slot.start_time,
                        end_time=end_datetime.time(),
                        duration_minutes=duration,
                        service_name=catalog_service.name if catalog_service else "Service",
                        hourly_rate=service.hourly_rate,
                        total_price=service.hourly_rate * (duration / 60),
                        status=BookingStatus.CONFIRMED,
                        service_area=instructor.instructor_profile.areas_of_service
                        if instructor.instructor_profile
                        else None,
                        meeting_location="Online",
                        location_type="neutral",
                    )
                    session.add(booking)
                    booking_count += 1

            session.commit()
            print(f"✅ Created {booking_count} sample bookings")

            # Create historical bookings for suspended/deactivated instructors
            self._create_historical_bookings_for_inactive_instructors(session)

    def _create_historical_bookings_for_inactive_instructors(self, session):
        """Create past bookings for suspended/deactivated instructors for testing"""
        historical_count = 0

        # Get suspended/deactivated instructors
        inactive_instructors = (
            session.query(User)
            .filter(
                User.role == UserRole.INSTRUCTOR,
                User.email.like("%@example.com"),
                User.account_status.in_(["suspended", "deactivated"]),
            )
            .all()
        )

        if not inactive_instructors:
            return

        # Get some students
        students = (
            session.query(User).filter(User.role == UserRole.STUDENT, User.email.like("%@example.com")).limit(3).all()
        )

        if not students:
            return

        for instructor in inactive_instructors:
            # Get instructor's services
            services = (
                session.query(InstructorService)
                .join(InstructorProfile)
                .filter(InstructorProfile.user_id == instructor.id)
                .all()
            )

            if not services:
                continue

            # Create 2-3 past bookings (completed)
            num_past_bookings = random.randint(2, 3)
            for i in range(num_past_bookings):
                service = random.choice(services)
                student = random.choice(students)
                duration = random.choice(service.duration_options)

                # Create a booking from 1-4 weeks ago
                days_ago = random.randint(7, 28)
                booking_date = date.today() - timedelta(days=days_ago)

                # Random time between 10 AM and 6 PM
                hour = random.randint(10, 17)
                start_time = time(hour, 0)
                end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=duration)).time()

                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor.id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=BookingStatus.COMPLETED,
                    location_type="online",
                    meeting_location="Zoom",
                    service_name=service.catalog_entry.name if service.catalog_entry else "Service",
                    service_area="Manhattan",
                    hourly_rate=service.hourly_rate,
                    total_price=service.session_price(duration),
                    duration_minutes=duration,
                    student_note=f"Historical booking for testing - {instructor.account_status} instructor",
                )
                session.add(booking)
                historical_count += 1

        session.commit()
        if historical_count > 0:
            print(f"  📚 Created {historical_count} historical bookings for inactive instructors")

    def print_summary(self):
        """Print summary of created data"""
        with Session(self.engine) as session:
            student_count = (
                session.query(User).filter(User.role == UserRole.STUDENT, User.email.like("%@example.com")).count()
            )
            instructor_count = (
                session.query(User).filter(User.role == UserRole.INSTRUCTOR, User.email.like("%@example.com")).count()
            )
            service_count = (
                session.query(InstructorService)
                .join(InstructorProfile)
                .join(User)
                .filter(User.email.like("%@example.com"))
                .count()
            )
            booking_count = (
                session.query(Booking)
                .join(User, Booking.student_id == User.id)
                .filter(User.email.like("%@example.com"))
                .count()
            )

            print("\n📊 Summary:")
            print(f"  Students: {student_count}")
            print(f"  Instructors: {instructor_count}")
            print(f"  Services: {service_count}")
            print(f"  Bookings: {booking_count}")


if __name__ == "__main__":
    seeder = DatabaseSeeder()
    seeder.seed_all()
