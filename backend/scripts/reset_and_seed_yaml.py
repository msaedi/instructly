#!/usr/bin/env python3
"""
Reset and seed database using YAML configuration files.

Usage:
  Default (INT database): python backend/scripts/reset_and_seed_yaml.py
  Staging database: SITE_MODE=local python backend/scripts/reset_and_seed_yaml.py
  Production: SITE_MODE=prod python backend/scripts/reset_and_seed_yaml.py (requires confirmation)
"""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from datetime import date, datetime, time, timedelta, timezone
import json
import random

# Add the scripts directory to Python path so imports work from anywhere
sys.path.insert(0, str(Path(__file__).parent))

from seed_catalog_only import seed_catalog
from seed_yaml_loader import SeedDataLoader
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import ulid

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PlatformCredit, StripeConnectedAccount
from app.models.rbac import Role, UserRole as UserRoleJunction
from app.models.review import Review, ReviewStatus
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.models.user import User
from app.repositories.address_repository import InstructorServiceAreaRepository
from app.repositories.region_boundary_repository import RegionBoundaryRepository


class DatabaseSeeder:
    def __init__(self):
        # Use absolute path based on script location
        seed_data_path = Path(__file__).parent / "seed_data"
        self.loader = SeedDataLoader(seed_data_dir=str(seed_data_path))
        self.engine = self._create_engine()
        self.created_users = {}
        self.created_services = {}
        self.stripe_mapping = self._load_stripe_mapping()

    def _create_engine(self):
        db_url = settings.get_database_url()
        # The DatabaseConfig will print which database is being used
        return create_engine(db_url)

    def _load_stripe_mapping(self):
        """Load Stripe test account mappings if file exists"""
        mapping_file = Path(__file__).parent.parent / "config" / "stripe_test_accounts.json"
        if mapping_file.exists():
            try:
                with open(mapping_file) as f:
                    mapping = json.load(f)
                    # Filter out the comment key
                    if "_comment" in mapping:
                        del mapping["_comment"]
                    print(f"📦 Loaded Stripe account mappings for {len(mapping)} instructors")
                    return mapping
            except Exception as e:
                print(f"⚠️  Could not load Stripe mappings: {e}")
                return {}
        else:
            print("ℹ️  No Stripe account mapping file found (config/stripe_test_accounts.json)")
            return {}

    def reset_database(self):
        """Clean test data from database"""
        with Session(self.engine) as session:
            # Delete in order to respect foreign key constraints
            print("🧹 Cleaning database...")

            # 1. Clean user-related data
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

            # 2. Clean service catalog data COMPLETELY
            print("  - Cleaning service catalog...")
            # Delete instructor services first (foreign key constraint)
            result = session.execute(text("DELETE FROM instructor_services"))
            print(f"    Deleted {result.rowcount} instructor services")

            # Delete service analytics
            result = session.execute(text("DELETE FROM service_analytics"))
            print(f"    Deleted {result.rowcount} service analytics")

            # Delete all services from catalog
            result = session.execute(text("DELETE FROM service_catalog"))
            print(f"    Deleted {result.rowcount} catalog services")

            # Delete all categories
            result = session.execute(text("DELETE FROM service_categories"))
            print(f"    Deleted {result.rowcount} service categories")

            # No sequences to reset - using ULIDs now

            # 3. Clean search history and search events
            print("  - Cleaning search history...")
            result = session.execute(text("DELETE FROM search_history"))
            print(f"    Deleted {result.rowcount} search history entries")

            print("  - Cleaning search events...")
            result = session.execute(text("DELETE FROM search_events"))
            print(f"    Deleted {result.rowcount} search event entries")

            # 4. Clean Stripe connected accounts
            print("  - Cleaning Stripe connected accounts...")
            result = session.execute(
                text(
                    "DELETE FROM stripe_connected_accounts WHERE instructor_profile_id IN "
                    "(SELECT id FROM instructor_profiles WHERE user_id IN "
                    "(SELECT id FROM users WHERE email LIKE '%@example.com'))"
                )
            )
            print(f"    Deleted {result.rowcount} Stripe connected accounts")

            # 5. Clean instructor profiles and users
            session.execute(
                text(
                    "DELETE FROM instructor_profiles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')"
                )
            )
            session.execute(
                text("DELETE FROM users WHERE email LIKE '%@example.com' OR email = 'admin@instainstru.com'")
            )

            session.commit()
            print("✅ Cleaned all test data, search history, and service catalog from database")

    def ensure_core_roles(self):
        """Ensure admin/instructor/student roles exist before seeding."""
        core_roles = {
            RoleName.ADMIN.value: "Platform administrators with full access",
            RoleName.INSTRUCTOR.value: "Instructors providing lessons on the platform",
            RoleName.STUDENT.value: "Students booking lessons",
        }
        with Session(self.engine) as session:
            existing = {
                role.name for role in session.query(Role).filter(Role.name.in_(tuple(core_roles)))
            }
            created = 0
            for name, description in core_roles.items():
                if name not in existing:
                    session.add(Role(name=name, description=description))
                    created += 1
            if created:
                session.commit()
                print(f"✅ Ensured {created} core role(s) are present")
            else:
                print("ℹ️ Core roles already present")

    def seed_all(self):
        """Main seeding function"""
        print("🌱 Starting database seeding...")
        self.reset_database()
        self.ensure_core_roles()

        # Seed service catalog first
        print("\n📚 Seeding service catalog...")
        db_url = self.engine.url.render_as_string(hide_password=False)
        _catalog_stats = seed_catalog(db_url=db_url, verbose=True)

        self.create_students()
        self.create_instructors()
        self.create_availability()
        self.create_coverage_areas()
        self.create_bookings()
        self.create_sample_platform_credits()
        self.create_reviews()
        self.print_summary()
        print("✅ Database seeding complete!")

    def create_students(self):
        """Create student accounts from YAML"""
        students = self.loader.get_students()
        password = self.loader.get_default_password()

        with Session(self.engine) as session:
            # Get roles
            admin_role = session.query(Role).filter_by(name=RoleName.ADMIN).first()
            student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()

            if not admin_role or not student_role:
                print("❌ Error: Roles not found. Make sure migrations ran successfully.")
                return

            for student_data in students:
                # Determine role based on email
                is_admin = student_data["email"] == "admin@instainstru.com"

                user = User(
                    email=student_data["email"],
                    first_name=student_data["first_name"],
                    last_name=student_data["last_name"],
                    phone=student_data.get("phone"),
                    zip_code=student_data["zip_code"],
                    hashed_password=get_password_hash(password),
                    is_active=True,
                    account_status="active",
                )
                session.add(user)
                session.flush()

                # Assign role
                role_to_assign = admin_role if is_admin else student_role
                user_role = UserRoleJunction(user_id=user.id, role_id=role_to_assign.id)
                session.add(user_role)

                self.created_users[user.email] = user.id
                role_text = "admin" if is_admin else "student"
                print(f"  ✅ Created {role_text}: {user.first_name} {user.last_name}")

            session.commit()
        print(f"✅ Created {len(students)} users (students and admins)")

    def create_instructors(self):
        """Create instructor accounts with profiles and services from YAML"""
        instructors = self.loader.get_instructors()
        password = self.loader.get_default_password()

        with Session(self.engine) as session:
            # Get instructor role
            instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()

            if not instructor_role:
                print("❌ Error: Instructor role not found. Make sure migrations ran successfully.")
                return

            for instructor_data in instructors:
                # Create user account
                # Allow account_status to be specified in YAML, default to "active"
                account_status = instructor_data.get("account_status", "active")
                user = User(
                    email=instructor_data["email"],
                    first_name=instructor_data["first_name"],
                    last_name=instructor_data["last_name"],
                    phone=instructor_data.get("phone"),
                    zip_code=instructor_data["zip_code"],
                    hashed_password=get_password_hash(password),
                    is_active=True,
                    account_status=account_status,
                )
                session.add(user)
                session.flush()

                # Assign instructor role
                user_role = UserRoleJunction(user_id=user.id, role_id=instructor_role.id)
                session.add(user_role)

                # Create instructor profile
                profile_data = instructor_data.get("profile", {})
                # Determine seeded onboarding status
                _has_services = len(profile_data.get("services", [])) > 0
                _is_active_account = account_status == "active"
                _now = datetime.now(timezone.utc)

                # Use values as-is from YAML (backend enforces validation at runtime)
                _bio = profile_data.get("bio", "").strip()
                _areas_list = profile_data.get("areas", [])

                profile = InstructorProfile(
                    user_id=user.id,
                    bio=_bio,
                    years_experience=profile_data.get("years_experience", 1),
                    areas_of_service=", ".join(_areas_list),
                    min_advance_booking_hours=2,
                    buffer_time_minutes=0,
                    # Onboarding defaults for seeded instructors
                    skills_configured=_has_services,
                    identity_verified_at=_now,
                    identity_verification_session_id=None,
                    background_check_object_key=None,
                    background_check_uploaded_at=None,
                    onboarding_completed_at=_now,
                    is_live=_is_active_account,
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

                    # Normalize age_groups to allowed values: 'kids' and 'adults' only
                    raw_groups = service_data.get("age_groups") or []
                    normalized_groups = []
                    for g in raw_groups:
                        v = str(g).strip().lower()
                        if v == "both":
                            for val in ("kids", "adults"):
                                if val not in normalized_groups:
                                    normalized_groups.append(val)
                            continue
                        if v in {"kids", "children", "child", "teen", "teens", "youth"}:
                            if "kids" not in normalized_groups:
                                normalized_groups.append("kids")
                            continue
                        if v in {"adult", "adults"}:
                            if "adults" not in normalized_groups:
                                normalized_groups.append("adults")
                            continue
                        # drop unknown values

                    # Default to 'adults' to match frontend behavior when unspecified
                    if not normalized_groups:
                        normalized_groups = ["adults"]

                    # Ensure ~20% of seeded services include kids for testing, if not already
                    try:
                        import random as _random

                        if ("kids" not in normalized_groups) and (_random.random() < 0.20):
                            normalized_groups.append("kids")
                    except Exception:
                        pass

                    # Create instructor service linked to catalog
                    service = InstructorService(
                        instructor_profile_id=profile.id,
                        service_catalog_id=catalog_service.id,
                        hourly_rate=service_data["price"],
                        description=service_data.get("description"),
                        duration_options=service_data.get("duration_options", [60]),
                        experience_level=service_data.get("experience_level"),
                        requirements=service_data.get("requirements"),
                        equipment_required=service_data.get("equipment_required"),
                        levels_taught=service_data.get("levels_taught"),
                        age_groups=normalized_groups or None,
                        location_types=service_data.get("location_types"),
                        max_distance_miles=service_data.get("max_distance_miles"),
                        is_active=True,
                    )
                    session.add(service)
                    session.flush()
                    self.created_services[f"{user.email}:{service_name}"] = service.id
                    service_count += 1

                # Create Stripe connected account if mapping exists
                if user.email in self.stripe_mapping and self.stripe_mapping[user.email]:
                    # Don't assume onboarding status - let the app check with Stripe dynamically
                    # This just restores the account association
                    stripe_account = StripeConnectedAccount(
                        id=str(ulid.ULID()),
                        instructor_profile_id=profile.id,
                        stripe_account_id=self.stripe_mapping[user.email],
                        onboarding_completed=True,
                        created_at=_now,
                        updated_at=_now,
                    )
                    session.add(stripe_account)
                    print(f"    💳 Linked to existing Stripe account: {self.stripe_mapping[user.email][:20]}...")

                self.created_users[user.email] = user.id
                status_info = f" [{account_status.upper()}]" if account_status != "active" else ""
                print(
                    f"  ✅ Created instructor: {user.first_name} {user.last_name} with {service_count} services{status_info}"
                )

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

    def create_coverage_areas(self):
        """Assign deterministic primary/secondary/by_request neighborhoods using repository pattern.

        Coverage rules are defined in seed_data/coverage.yaml, allowing per-instructor overrides
        by email, and default Manhattan neighborhoods otherwise.
        """
        with Session(self.engine) as session:
            isa_repo = InstructorServiceAreaRepository(session)
            region_repo = RegionBoundaryRepository(session)

            rules = self.loader.get_coverage_rules()
            defaults = rules.get(
                "defaults",
                {
                    "names": [
                        {"name": "Upper West Side", "coverage_type": "primary"},
                        {"name": "Upper East Side", "coverage_type": "secondary"},
                        {"name": "Midtown", "coverage_type": "by_request"},
                    ]
                },
            )

            # Resolve ids for all distinct names in one pass
            all_names = []
            for cfg in defaults.get("names", []):
                all_names.append(cfg["name"])
            overrides = rules.get("overrides", {})
            for ov in overrides.values():
                for cfg in ov.get("names", []):
                    all_names.append(cfg["name"])
            name_to_id = region_repo.find_region_ids_by_partial_names(list(dict.fromkeys(all_names)))

            # Assign to each example instructor
            for email, user_id in self.created_users.items():
                if not email.endswith("@example.com"):
                    continue
                # Skip non-instructors
                with session.no_autoflush:
                    user = session.query(User).filter(User.id == user_id).first()
                    if not user or not any(r.name == RoleName.INSTRUCTOR for r in user.roles):
                        continue

                # Pick config: override by email, else defaults
                cfg = overrides.get(email, defaults)
                for item in cfg.get("names", []):
                    rid = name_to_id.get(item["name"]) if item.get("name") else None
                    if not rid:
                        continue
                    isa_repo.upsert_area(
                        instructor_id=user_id,
                        neighborhood_id=rid,
                        coverage_type=item.get("coverage_type"),
                        max_distance_miles=float(cfg.get("max_distance_miles", 2.0)),
                        is_active=True,
                    )

            session.commit()
            print("✅ Assigned instructor coverage areas from YAML rules")

    def create_availability(self):
        """Create availability slots based on patterns"""
        instructors = self.loader.get_instructors()
        settings_cfg = self.loader.config.get("settings", {})
        weeks_future = settings_cfg.get("availability_weeks_future")
        weeks_past = settings_cfg.get("availability_weeks_past")

        # Backwards compat: fall back to legacy single setting
        if weeks_future is None:
            legacy_weeks = settings_cfg.get("weeks_of_availability", 4)
            weeks_future = legacy_weeks
        if weeks_past is None:
            weeks_past = 0

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
                # Generate slots for past weeks (if configured), current week, and future weeks
                for week_offset in range(-weeks_past, weeks_future + 1):
                    for day_name, time_slots in days_data.items():
                        # Calculate the date for this day
                        target_date = self._get_date_for_day(day_name, week_offset)

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
                print(
                    f"  ✅ Created availability for {instructor_data['first_name']} {instructor_data['last_name']} using pattern '{pattern_name}'"
                )

        print("✅ Created availability patterns for all instructors")

    def _get_date_for_day(self, day_name: str, week_offset: int) -> date:
        """Return the calendar date for a given day name within the week offset."""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        day_index = days.index(day_name.lower())

        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Monday of the current week
        target_week_start = start_of_week + timedelta(weeks=week_offset)
        return target_week_start + timedelta(days=day_index)

    def _day_name_to_number(self, day_name):
        """Convert day name to number (0=Monday, 6=Sunday)"""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return days.index(day_name.lower())

    def create_bookings(self):
        """Create sample bookings for testing"""
        settings_cfg = self.loader.config.get("settings", {})
        booking_days_future = settings_cfg.get("booking_days_future", settings_cfg.get("booking_days_ahead", 7))
        booking_days_past = settings_cfg.get("booking_days_past", 21)

        with Session(self.engine) as session:
            # Get all students
            # Get students by joining with roles
            student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
            students = (
                session.query(User)
                .join(UserRoleJunction)
                .filter(UserRoleJunction.role_id == student_role.id, User.email.like("%@example.com"))
                .all()
            )

            if not students:
                print("  ⚠️  No students found to create bookings")
                return

            # Exclude Emma Fresh from getting bookings (for testing "How It Works" section)
            students = [s for s in students if s.email != "emma.fresh@example.com"]
            print(f"  📝 Creating bookings for {len(students)} students (excluding emma.fresh@example.com)")

            booking_count = 0

            # For each instructor, create 1-3 bookings
            for instructor_email, instructor_id in self.created_users.items():
                if not instructor_email.endswith("@example.com"):
                    continue

                # Skip students
                instructor = session.query(User).filter(User.id == instructor_id).first()
                if not any(role.name == RoleName.INSTRUCTOR for role in instructor.roles):
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
                            AvailabilitySlot.specific_date <= date.today() + timedelta(days=booking_days_future),
                        )
                        .all()
                    )

                    if not slots:
                        continue

                    # Pick a random slot
                    slot = random.choice(slots)

                    # Calculate end time based on duration
                    start_datetime = datetime.combine(slot.specific_date, slot.start_time)
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
            self._create_historical_bookings_for_inactive_instructors(session, booking_days_past)

            # Create completed bookings for active students (for testing Book Again)
        self._create_completed_bookings_for_active_students(session, booking_days_past)

    def _create_historical_bookings_for_inactive_instructors(self, session, booking_days_past: int):
        """Create past bookings for suspended/deactivated instructors for testing"""
        historical_count = 0

        # Get suspended/deactivated instructors
        instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
        inactive_instructors = (
            session.query(User)
            .join(UserRoleJunction)
            .filter(
                UserRoleJunction.role_id == instructor_role.id,
                User.email.like("%@example.com"),
                User.account_status.in_(["suspended", "deactivated"]),
            )
            .all()
        )

        if not inactive_instructors:
            return

        # Get some students
        student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
        students = (
            session.query(User)
            .join(UserRoleJunction)
            .filter(UserRoleJunction.role_id == student_role.id, User.email.like("%@example.com"))
            .limit(3)
            .all()
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
                days_ago = random.randint(7, max(7, booking_days_past))
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
                    location_type="neutral",
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

    def _create_completed_bookings_for_active_students(self, session, booking_days_past: int):
        """Create completed bookings for active students with active instructors (for testing Book Again)"""
        completed_count = 0

        # Get active students
        student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
        active_students = (
            session.query(User)
            .join(UserRoleJunction)
            .filter(
                UserRoleJunction.role_id == student_role.id,
                User.email.like("%@example.com"),
                User.account_status == "active",
            )
            .all()
        )

        # Get active instructors
        instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
        active_instructors = (
            session.query(User)
            .join(UserRoleJunction)
            .filter(
                UserRoleJunction.role_id == instructor_role.id,
                User.email.like("%@example.com"),
                User.account_status == "active",
            )
            .all()
        )

        if not active_students or not active_instructors:
            print("  ⚠️  No active students or instructors found for completed bookings")
            return

        # Create completed bookings for Emma Johnson specifically (and other students)
        for student in active_students:
            # Create 2-3 completed bookings per student
            num_completed = random.randint(2, 3)

            for _ in range(num_completed):
                # Pick a random active instructor
                instructor = random.choice(active_instructors)

                # Get instructor's services
                services = (
                    session.query(InstructorService)
                    .join(InstructorProfile)
                    .filter(InstructorProfile.user_id == instructor.id)
                    .all()
                )

                if not services:
                    continue

                service = random.choice(services)
                duration = random.choice(service.duration_options)

                # Create a booking from 1-8 weeks ago (in the past)
                days_ago = random.randint(7, max(7, booking_days_past))
                booking_date = date.today() - timedelta(days=days_ago)

                # Random time between 10 AM and 6 PM
                hour = random.randint(10, 17)
                start_time = time(hour, 0)
                end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=duration)).time()

                # Get service details from catalog
                catalog_service = session.query(ServiceCatalog).filter_by(id=service.service_catalog_id).first()

                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor.id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=BookingStatus.COMPLETED,
                    location_type="neutral",
                    meeting_location="In-person",
                    service_name=catalog_service.name if catalog_service else "Service",
                    service_area="Manhattan",
                    hourly_rate=service.hourly_rate,
                    total_price=service.hourly_rate * (duration / 60),
                    duration_minutes=duration,
                    student_note="Completed lesson for testing Book Again feature",
                    completed_at=datetime.now() - timedelta(days=days_ago - 1),  # Mark as completed day after booking
                )
                session.add(booking)
                completed_count += 1

        session.commit()
        if completed_count > 0:
            print(f"  🎯 Created {completed_count} completed bookings for active students (Book Again testing)")

    def create_reviews(self):
        """Create 3 published reviews per active instructor to enable ratings display."""
        with Session(self.engine) as session:
            try:
                instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
                student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
                if not instructor_role or not student_role:
                    print("  ⚠️  Roles not found; skipping review seeding")
                    return

                # Active instructors seeded from YAML
                active_instructors = (
                    session.query(User)
                    .join(UserRoleJunction)
                    .filter(
                        UserRoleJunction.role_id == instructor_role.id,
                        User.email.like("%@example.com"),
                        User.account_status == "active",
                    )
                    .all()
                )

                total_reviews_created = 0

                for instructor in active_instructors:
                    # Gather completed bookings for this instructor
                    completed_bookings = (
                        session.query(Booking)
                        .filter(
                            Booking.instructor_id == instructor.id,
                            Booking.status == BookingStatus.COMPLETED,
                        )
                        .order_by(Booking.booking_date.desc())
                        .all()
                    )

                    # Ensure at least 3 completed bookings exist by synthesizing if needed
                    while len(completed_bookings) < 3:
                        services = (
                            session.query(InstructorService)
                            .join(InstructorProfile)
                            .filter(InstructorProfile.user_id == instructor.id)
                            .all()
                        )
                        if not services:
                            break

                        # Pick a random active student
                        student = (
                            session.query(User)
                            .join(UserRoleJunction)
                            .filter(
                                UserRoleJunction.role_id == student_role.id,
                                User.email.like("%@example.com"),
                                User.account_status == "active",
                            )
                            .first()
                        )
                        if not student:
                            break

                        service = random.choice(services)
                        duration = random.choice(service.duration_options)
                        days_ago = random.randint(7, 56)
                        booking_date = date.today() - timedelta(days=days_ago)
                        hour = random.randint(10, 17)
                        start_time = time(hour, 0)
                        end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=duration)).time()

                        # Create a completed booking in the past
                        new_booking = Booking(
                            student_id=student.id,
                            instructor_id=instructor.id,
                            instructor_service_id=service.id,
                            booking_date=booking_date,
                            start_time=start_time,
                            end_time=end_time,
                            status=BookingStatus.COMPLETED,
                            location_type="neutral",
                            meeting_location="In-person",
                            service_name=service.catalog_entry.name if service.catalog_entry else "Service",
                            service_area=(
                                instructor.instructor_profile.areas_of_service
                                if instructor.instructor_profile
                                else None
                            ),
                            hourly_rate=service.hourly_rate,
                            total_price=service.hourly_rate * (duration / 60),
                            duration_minutes=duration,
                            student_note="Seeded completed booking for reviews",
                            completed_at=datetime.now(timezone.utc) - timedelta(days=days_ago - 1),
                        )
                        session.add(new_booking)
                        session.flush()
                        completed_bookings.append(new_booking)

                    # Create up to 3 reviews on completed bookings
                    for booking in completed_bookings[:3]:
                        # Skip if a review already exists
                        exists = session.query(Review).filter(Review.booking_id == booking.id).first()
                        if exists:
                            continue

                        # Rating distribution biased toward 4-5
                        rating_value = random.choices([5, 4, 3], weights=[60, 30, 10])[0]
                        sample_texts = [
                            "Great lesson, very helpful and patient.",
                            "Clear explanations and good pace.",
                            "Enjoyable session; learned a lot.",
                            "Professional and friendly instructor.",
                            "Challenging but rewarding lesson.",
                        ]
                        review_text = random.choice(sample_texts)

                        completed_at = booking.completed_at
                        if not completed_at:
                            # Derive completion timestamp from booking date/time
                            base_dt = datetime.combine(
                                booking.booking_date or date.today(),
                                (booking.end_time or booking.start_time or time(23, 0)),
                            )
                            completed_at = base_dt.replace(tzinfo=timezone.utc)
                        elif completed_at.tzinfo is None:
                            completed_at = completed_at.replace(tzinfo=timezone.utc)

                        review = Review(
                            booking_id=booking.id,
                            student_id=booking.student_id,
                            instructor_id=booking.instructor_id,
                            instructor_service_id=booking.instructor_service_id,
                            rating=rating_value,
                            review_text=review_text,
                            status=ReviewStatus.PUBLISHED,
                            is_verified=True,
                            booking_completed_at=completed_at,
                        )
                        session.add(review)
                        total_reviews_created += 1

                session.commit()
                print(f"✅ Seeded {total_reviews_created} reviews for active instructors")
            except Exception as e:
                session.rollback()
                print(f"  ⚠️  Skipped review seeding due to error: {e}")

    def print_summary(self):
        """Print summary of created data"""
        with Session(self.engine) as session:
            # Get role IDs
            student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
            instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()

            student_count = (
                session.query(User)
                .join(UserRoleJunction)
                .filter(UserRoleJunction.role_id == student_role.id, User.email.like("%@example.com"))
                .count()
            )
            instructor_count = (
                session.query(User)
                .join(UserRoleJunction)
                .filter(UserRoleJunction.role_id == instructor_role.id, User.email.like("%@example.com"))
                .count()
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

            # Count platform credits for visibility
            credits_count = session.query(PlatformCredit).count()

            print("\n📊 Summary:")
            print(f"  Students: {student_count}")
            print(f"  Instructors: {instructor_count}")
            print(f"  Services: {service_count}")
            print(f"  Bookings: {booking_count}")
            print(f"  Platform Credits: {credits_count}")

    def create_sample_platform_credits(self):
        """Create sample platform credits for specific test users."""
        from datetime import timedelta


        with Session(self.engine) as session:
            # Find Emma Johnson
            emma = session.query(User).filter(User.email == "emma.johnson@example.com").first()
            if not emma:
                print("  ⚠️  Emma Johnson not found; skipping platform credit seeding")
                return

            now = datetime.now(timezone.utc)

            # $20 credit expiring in 30 days
            c1 = PlatformCredit(
                user_id=emma.id,
                amount_cents=2000,
                reason="seed: test credit",
                expires_at=now + timedelta(days=30),
            )
            session.add(c1)

            # $25 credit expiring in 90 days
            c2 = PlatformCredit(
                user_id=emma.id,
                amount_cents=2500,
                reason="seed: test credit",
                expires_at=now + timedelta(days=90),
            )
            session.add(c2)

            session.commit()
            print("✅ Seeded platform credits for emma.johnson@example.com: $20 (30d), $25 (90d)")


if __name__ == "__main__":
    seeder = DatabaseSeeder()
    seeder.seed_all()
