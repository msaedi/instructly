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
from decimal import Decimal
import json
import os
import random
from typing import Any, Sequence

# Add the scripts directory to Python path so imports work from anywhere
sys.path.insert(0, str(Path(__file__).parent))

from seed_catalog_only import seed_catalog
from seed_utils import create_review_booking_pg_safe
from seed_yaml_loader import SeedDataLoader
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session
import ulid

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.models.availability import AvailabilitySlot
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.instructor import BGCConsent, InstructorProfile
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
        self.instructor_seed_plan = {}

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

    @staticmethod
    def _get_env_int(key: str, default: int) -> int:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @staticmethod
    def _get_env_csv_ints(key: str, default: Sequence[int]) -> list[int]:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return list(default)
        values: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(int(part))
            except ValueError:
                continue
        return values or list(default)

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
        self._prepare_bitmap_environment()
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

            created_count = 0
            skipped_existing = 0

            for student_data in students:
                # Determine role based on email
                is_admin = student_data["email"] == "admin@instainstru.com"

                existing_user = (
                    session.query(User).filter(User.email == student_data["email"]).one_or_none()
                )
                role_to_assign = admin_role if is_admin else student_role

                if existing_user:
                    skipped_existing += 1
                    # Ensure the expected role exists for the user
                    has_role = (
                        session.query(UserRoleJunction)
                        .filter(
                            UserRoleJunction.user_id == existing_user.id,
                            UserRoleJunction.role_id == role_to_assign.id,
                        )
                        .first()
                        is not None
                    )
                    if not has_role:
                        session.add(UserRoleJunction(user_id=existing_user.id, role_id=role_to_assign.id))
                    self.created_users[existing_user.email] = existing_user.id
                    role_text = "admin" if is_admin else "student"
                    print(f"  ℹ️  {role_text.title()} {existing_user.email} already exists; skipping create")
                    continue

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
                user_role = UserRoleJunction(user_id=user.id, role_id=role_to_assign.id)
                session.add(user_role)

                self.created_users[user.email] = user.id
                role_text = "admin" if is_admin else "student"
                print(f"  ✅ Created {role_text}: {user.first_name} {user.last_name}")
                created_count += 1

            session.commit()
        total = created_count + skipped_existing
        summary = f"✅ Created {created_count} users"
        if skipped_existing:
            summary += f" (skipped {skipped_existing} existing)"
        summary += f" (total defined: {total})"
        print(summary)

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

                current_tier_pct_value = float(instructor_data.get("current_tier_pct", 15.00))
                seed_completed_last_30d = int(instructor_data.get("seed_completed_last_30d") or 0)
                seed_randomize_categories = bool(instructor_data.get("seed_randomize_categories", False))

                profile = InstructorProfile(
                    user_id=user.id,
                    bio=_bio,
                    years_experience=profile_data.get("years_experience", 1),
                    min_advance_booking_hours=2,
                    buffer_time_minutes=0,
                    current_tier_pct=current_tier_pct_value,
                    last_tier_eval_at=_now,
                    # Onboarding defaults for seeded instructors
                    skills_configured=_has_services,
                    identity_verified_at=_now,
                    identity_verification_session_id=None,
                    background_check_object_key=None,
                    background_check_uploaded_at=None,
                    onboarding_completed_at=_now,
                    is_live=_is_active_account,
                )
                if os.getenv("SEED_FORCE_BGC_PASSED", "1") == "1" and profile.is_live:
                    now_utc = datetime.now(timezone.utc)
                    profile.bgc_status = "passed"
                    profile.bgc_env = profile.bgc_env or "sandbox"
                    profile.bgc_completed_at = now_utc

                session.add(profile)
                session.flush()

                plan_entry = {
                    "user_id": user.id,
                    "profile_id": profile.id,
                    "seed_completed_last_30d": seed_completed_last_30d,
                    "seed_randomize_categories": seed_randomize_categories,
                    "service_ids": [],
                }
                self.instructor_seed_plan[user.email] = plan_entry

                if os.getenv("SEED_FORCE_BGC_PASSED", "1") == "1" and profile.is_live:
                    now_utc = profile.bgc_completed_at or datetime.now(timezone.utc)
                    session.add(
                        BGCConsent(
                            instructor_id=profile.id,
                            consent_version="seed.v1",
                            consented_at=now_utc,
                            ip_address="127.0.0.1",
                        )
                    )

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
                    plan_entry["service_ids"].append(service.id)

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

            self._seed_tier_maintenance_sessions(session)
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

    def _seed_tier_maintenance_sessions(self, session: Session) -> None:
        """Seed completed sessions in the last 30 days to preserve tier assignments."""

        if not self.instructor_seed_plan:
            return

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=30)

        student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
        if not student_role:
            return

        students = (
            session.query(User)
            .join(UserRoleJunction, UserRoleJunction.user_id == User.id)
            .filter(UserRoleJunction.role_id == student_role.id, User.email.like("%@example.com"))
            .all()
        )

        if not students:
            print("  ⚠️  Skipping tier maintenance seeding: no seed students available")
            return

        rng = random.Random(42)
        total_seeded = 0

        for email, plan in self.instructor_seed_plan.items():
            desired = int(plan.get("seed_completed_last_30d") or 0)
            if desired <= 0:
                continue

            user_id = plan.get("user_id")
            if not user_id:
                continue

            existing_count = (
                session.query(Booking)
                .filter(
                    Booking.instructor_id == user_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at >= window_start,
                )
                .count()
            )

            remaining = desired - existing_count
            if remaining <= 0:
                continue

            service_ids = plan.get("service_ids") or []
            if not service_ids:
                continue

            services = (
                session.query(InstructorService)
                .filter(InstructorService.id.in_(service_ids))
                .all()
            )

            if not services:
                continue

            for _ in range(remaining):
                if plan.get("seed_randomize_categories") and len(services) > 1:
                    service = rng.choice(services)
                else:
                    service = services[0]

                duration_options = service.duration_options or [60]
                duration = int(rng.choice(duration_options)) or 60

                days_ago = rng.randint(0, 29)
                booking_date = (now - timedelta(days=days_ago)).date()

                start_hour = rng.randint(9, 18)
                start_time = time(start_hour, 0)
                start_dt_naive = datetime.combine(booking_date, start_time)
                end_dt_naive = start_dt_naive + timedelta(minutes=duration)
                end_time = end_dt_naive.time()

                start_dt = start_dt_naive.replace(tzinfo=timezone.utc)
                end_dt = end_dt_naive.replace(tzinfo=timezone.utc)

                loc_types = [lt.lower() for lt in (service.location_types or [])]
                is_remote = any(lt in {"online", "remote", "virtual"} for lt in loc_types)
                location_type = "remote" if is_remote else "student_home"
                meeting_location = "Online" if is_remote else "Student location"

                student = rng.choice(students)

                hourly_rate = Decimal(str(service.hourly_rate)).quantize(Decimal("0.01"))
                total_price = (hourly_rate * Decimal(duration) / Decimal(60)).quantize(Decimal("0.01"))

                service_name = (
                    service.catalog_entry.name
                    if service.catalog_entry
                    else (service.description or service.name)
                )

                booking = Booking(
                    student_id=student.id,
                    instructor_id=user_id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    duration_minutes=duration,
                    service_name=service_name,
                    hourly_rate=hourly_rate,
                    total_price=total_price,
                    status=BookingStatus.COMPLETED,
                    location_type=location_type,
                    meeting_location=meeting_location,
                    service_area=None,
                    student_note="Seeded maintenance session",
                    created_at=start_dt - timedelta(days=1),
                    confirmed_at=start_dt - timedelta(hours=2),
                    completed_at=end_dt,
                )
                session.add(booking)
                total_seeded += 1

        if total_seeded:
            print(f"  🎯 Seeded {total_seeded} maintenance sessions to preserve tier assignments")

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

    def _prepare_bitmap_environment(self):
        if os.getenv("BITMAP_PIPELINE_COMPLETED") == "1":
            print("  ℹ️  Bitmap pipeline already executed earlier in this run; skipping local seed/backfill.")
            return
        flag = os.getenv("SEED_AVAILABILITY_BITMAP", "0").lower() in {"1", "true", "yes"}
        if not flag:
            return

        weeks = self._get_env_int("SEED_AVAILABILITY_BITMAP_WEEKS", 3)
        print(f"🗓️  Seeding bitmap availability for {weeks} future week(s)…")
        from scripts.seed_bitmap_availability import seed_bitmap_availability

        result = seed_bitmap_availability(weeks)
        if result:
            for week_start, count in sorted(result.items()):
                print(f"  ✅ Bitmap week {week_start}: upserted {count} instructor(s)")
        else:
            print("  ℹ️  Bitmap availability seeder had no work.")

        backfill_days = self._get_env_int("BITMAP_BACKFILL_DAYS", 56)
        from scripts.backfill_bitmaps import backfill_bitmaps_range

        with Session(self.engine) as session:
            stats = backfill_bitmaps_range(session, backfill_days)
            if stats:
                session.commit()
                for instructor_id, days_written in sorted(stats.items()):
                    print(f"  ↩︎ Backfilled {days_written} day(s) of bitmap availability for instructor {instructor_id}")
            else:
                session.rollback()
                print("  ℹ️  No bitmap backfill required (coverage already present).")

    def _sample_bitmap_coverage(
        self,
        session: Session,
        instructor_ids: Sequence[str],
        lookback_days: int,
        horizon_days: int,
        sample_size: int = 3,
    ) -> dict:
        window_start = date.today() - timedelta(days=lookback_days)
        window_end = date.today() + timedelta(days=horizon_days)

        sample_ids: list[str] = []
        if instructor_ids:
            shuffled = list(instructor_ids)
            random.shuffle(shuffled)
            sample_ids = shuffled[: min(sample_size, len(shuffled))]

        sample_stats: list[tuple[str, int]] = []
        for instructor_id in sample_ids:
            count = (
                session.query(func.count(AvailabilityDay.day_date))
                .filter(
                    AvailabilityDay.instructor_id == instructor_id,
                    AvailabilityDay.day_date >= window_start,
                    AvailabilityDay.day_date <= window_end,
                )
                .scalar()
            )
            sample_stats.append((instructor_id, count or 0))

        total_rows = (
            session.query(func.count(AvailabilityDay.day_date))
            .filter(
                AvailabilityDay.day_date >= window_start,
                AvailabilityDay.day_date <= window_end,
            )
            .scalar()
        )

        return {
            "sample": sample_stats,
            "total_rows": total_rows or 0,
        }

    def create_bookings(self) -> int:
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
                return 0

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

                    # Check if this time is already booked for instructor
                    existing = (
                        session.query(Booking)
                        .filter(
                            Booking.instructor_id == instructor_id,
                            Booking.booking_date == slot.specific_date,
                            Booking.start_time < end_datetime.time(),
                            Booking.end_time > slot.start_time,
                            Booking.status.in_(
                                [
                                    BookingStatus.PENDING,
                                    BookingStatus.CONFIRMED,
                                    BookingStatus.COMPLETED,
                                ]
                            ),
                        )
                        .first()
                    )

                    if existing:
                        continue

                    # Prevent the student from having overlapping bookings
                    student_conflict = (
                        session.query(Booking)
                        .filter(
                            Booking.student_id == student.id,
                            Booking.booking_date == slot.specific_date,
                            Booking.start_time < end_datetime.time(),
                            Booking.end_time > slot.start_time,
                            Booking.status.in_(
                                [
                                    BookingStatus.PENDING,
                                    BookingStatus.CONFIRMED,
                                    BookingStatus.COMPLETED,
                                ]
                            ),
                        )
                        .first()
                    )

                    if student_conflict:
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
                        service_area=None,
                        meeting_location="Online",
                        location_type="neutral",
                    )
                    session.add(booking)
                    booking_count += 1

            session.commit()
            self._create_historical_bookings_for_inactive_instructors(session, booking_days_past)
            self._create_completed_bookings_for_active_students(session, booking_days_past)
            if booking_count:
                print(f"  ✅ Created {booking_count} sample bookings")
            return booking_count

        return 0

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

                # Skip if this student already has a booking overlapping this window
                student_overlap = (
                    session.query(Booking)
                    .filter(
                        Booking.student_id == student.id,
                        Booking.booking_date == booking_date,
                        Booking.start_time < end_time,
                        Booking.end_time > start_time,
                        Booking.status.in_(
                            [
                                BookingStatus.PENDING,
                                BookingStatus.CONFIRMED,
                                BookingStatus.COMPLETED,
                            ]
                        ),
                    )
                    .first()
                )

                if student_overlap:
                    continue

                instructor_overlap = (
                    session.query(Booking)
                    .filter(
                        Booking.instructor_id == instructor.id,
                        Booking.booking_date == booking_date,
                        Booking.start_time < end_time,
                        Booking.end_time > start_time,
                        Booking.status.in_(
                            [
                                BookingStatus.PENDING,
                                BookingStatus.CONFIRMED,
                                BookingStatus.COMPLETED,
                            ]
                        ),
                    )
                    .first()
                )

                if instructor_overlap:
                    continue

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
                    service_area=None,
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

                # Prevent overlaps with the student's existing bookings
                student_overlap = (
                    session.query(Booking)
                    .filter(
                        Booking.student_id == student.id,
                        Booking.booking_date == booking_date,
                        Booking.start_time < end_time,
                        Booking.end_time > start_time,
                        Booking.status.in_(
                            [
                                BookingStatus.PENDING,
                                BookingStatus.CONFIRMED,
                                BookingStatus.COMPLETED,
                            ]
                        ),
                    )
                    .first()
                )

                if student_overlap:
                    continue

                instructor_overlap = (
                    session.query(Booking)
                    .filter(
                        Booking.instructor_id == instructor.id,
                        Booking.booking_date == booking_date,
                        Booking.start_time < end_time,
                        Booking.end_time > start_time,
                        Booking.status.in_(
                            [
                                BookingStatus.PENDING,
                                BookingStatus.CONFIRMED,
                                BookingStatus.COMPLETED,
                            ]
                        ),
                    )
                    .first()
                )

                if instructor_overlap:
                    continue

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

    def create_reviews(self, strict: bool = False) -> int:
        """Create 3 published reviews per active instructor to enable ratings display."""
        with Session(self.engine) as session:
            try:
                instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
                student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
                if not instructor_role or not student_role:
                    print("  ⚠️  Roles not found; skipping review seeding")
                    return 0

                seed_horizon = self._get_env_int("SEED_REVIEW_HORIZON_DAYS", 21)
                seed_lookback = self._get_env_int("SEED_REVIEW_LOOKBACK_DAYS", 90)
                seed_day_start = self._get_env_int("SEED_REVIEW_DAY_START_HOUR", 9)
                seed_day_end = self._get_env_int("SEED_REVIEW_DAY_END_HOUR", 18)
                seed_step_minutes = self._get_env_int("SEED_REVIEW_STEP_MINUTES", 15)
                seed_durations = self._get_env_csv_ints("SEED_REVIEW_DURATIONS", [60, 45, 30])
                preferred_student_email = os.getenv("SEED_REVIEW_STUDENT_EMAIL", "").strip() or None

                probe_snapshot: dict[str, Any] | None = None
                probe_raw = os.getenv("BITMAP_PROBE_RESULT")
                if probe_raw:
                    try:
                        probe_snapshot = json.loads(probe_raw)
                    except json.JSONDecodeError:
                        probe_snapshot = None

                if probe_snapshot and int(probe_snapshot.get("total_rows", 0) or 0) == 0:
                    sample_items = probe_snapshot.get("sample") or []
                    sample_summary = ", ".join(
                        f"{(item.get('instructor_id') or '')[-6:]}:{item.get('rows', 0)}"
                        for item in sample_items[:3]
                    ) or "none"
                    print(
                        f"  ⚠️  Bitmap coverage probe reported zero rows; skipping review seeding "
                        f"(sample={sample_summary})"
                    )
                    return 0

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

                instructor_ids = [instructor.id for instructor in active_instructors]
                coverage_stats = self._sample_bitmap_coverage(
                    session,
                    instructor_ids,
                    seed_lookback,
                    seed_horizon,
                )
                sample_stats = coverage_stats["sample"]
                total_rows = coverage_stats["total_rows"]

                print(f"  🔍 Bitmap coverage probe (lookback {seed_lookback}d, horizon {seed_horizon}d):")
                if sample_stats:
                    print(f"  → Sampled {len(sample_stats)} instructor(s):")
                    for inst_id, count in sample_stats:
                        print(f"    • Instructor {inst_id[-8:]}: {count} bitmap row(s)")
                    formatted_sample = ", ".join(f"{inst[-6:]}:{count}" for inst, count in sample_stats)
                    print(f"  → Sample summary: {formatted_sample}")
                else:
                    print("  → No instructors found to sample")
                print(f"  → Total bitmap rows in window: {total_rows}")

                if total_rows == 0:
                    message = (
                        f"No bitmap availability found in the last {seed_lookback} days. "
                        "Run: SEED_AVAILABILITY_BITMAP=1 ... prep_db.py --seed-all"
                    )
                    print(f"  ❌  {message}")
                    if strict:
                        raise RuntimeError(message)
                    return 0

                preferred_student = None
                if preferred_student_email:
                    preferred_student = (
                        session.query(User)
                        .join(UserRoleJunction)
                        .filter(
                            UserRoleJunction.role_id == student_role.id,
                            User.email == preferred_student_email,
                            User.account_status == "active",
                        )
                        .first()
                    )
                    if not preferred_student:
                        print(
                            f"  ⚠️  Preferred review student '{preferred_student_email}' not found; using random students."
                        )

                total_reviews_created = 0

                for instructor in active_instructors:
                    completed_bookings = (
                        session.query(Booking)
                        .filter(
                            Booking.instructor_id == instructor.id,
                            Booking.status == BookingStatus.COMPLETED,
                        )
                        .order_by(Booking.booking_date.desc())
                        .all()
                    )

                    while len(completed_bookings) < 3:
                        services = (
                            session.query(InstructorService)
                            .join(InstructorProfile)
                            .filter(InstructorProfile.user_id == instructor.id)
                            .all()
                        )
                        if not services:
                            break

                        if preferred_student:
                            student = preferred_student
                        else:
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
                        base_date = date.today() - timedelta(days=days_ago)
                        helper_completed_at = datetime.now(timezone.utc) - timedelta(days=days_ago - 1)

                        new_booking = create_review_booking_pg_safe(
                            session,
                            student_id=student.id,
                            instructor_id=instructor.id,
                            instructor_service_id=service.id,
                            base_date=base_date,
                            location_type="neutral",
                            meeting_location="In-person",
                            service_name=service.catalog_entry.name if service.catalog_entry else "Service",
                            hourly_rate=service.hourly_rate,
                            total_price=service.hourly_rate * (duration / 60),
                            student_note="Seeded completed booking for reviews",
                            completed_at=helper_completed_at,
                            service_area=None,
                            duration_minutes=duration,
                            horizon_days=seed_horizon,
                            lookback_days=seed_lookback,
                            day_start_hour=seed_day_start,
                            day_end_hour=seed_day_end,
                            step_minutes=seed_step_minutes,
                            durations_minutes=seed_durations,
                        )

                        if not new_booking:
                            print(
                                f"  ⚠️  Skipping synthetic booking for reviews (instructor={instructor.id}); see structured log output."
                            )
                            break

                        completed_bookings.append(new_booking)

                    for booking in completed_bookings[:3]:
                        exists = session.query(Review).filter(Review.booking_id == booking.id).first()
                        if exists:
                            continue

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
                print(f"✅ Seeded {total_reviews_created} published reviews for active instructors")
                return total_reviews_created
            except Exception as e:
                session.rollback()
                print(f"  ⚠️  Skipped review seeding due to error: {e}")
                if strict:
                    raise
                return 0

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

    def create_sample_platform_credits(self) -> int:
        """Create sample platform credits for specific test users."""
        from datetime import timedelta


        with Session(self.engine) as session:
            # Find Emma Johnson
            emma = session.query(User).filter(User.email == "emma.johnson@example.com").first()
            if not emma:
                print("  ⚠️  Emma Johnson not found; skipping platform credit seeding")
                return 0

            now = datetime.now(timezone.utc)
            created = 0

            # $20 credit expiring in 30 days
            c1 = PlatformCredit(
                user_id=emma.id,
                amount_cents=2000,
                reason="seed: test credit",
                expires_at=now + timedelta(days=30),
            )
            session.add(c1)
            created += 1

            # $25 credit expiring in 90 days
            c2 = PlatformCredit(
                user_id=emma.id,
                amount_cents=2500,
                reason="seed: test credit",
                expires_at=now + timedelta(days=90),
            )
            session.add(c2)
            created += 1

            session.commit()
            print("✅ Seeded platform credits for emma.johnson@example.com: $20 (30d), $25 (90d)")
            return created


if __name__ == "__main__":
    seeder = DatabaseSeeder()
    seeder.seed_all()
