#!/usr/bin/env python3
"""
Reset and seed database using YAML configuration files.

Usage:
  Default (INT database): python backend/scripts/reset_and_seed_yaml.py
  Staging database: SITE_MODE=local python backend/scripts/reset_and_seed_yaml.py
  Production: SITE_MODE=prod python backend/scripts/reset_and_seed_yaml.py (requires confirmation)
"""

from collections import Counter
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path
import re
import sys

sys.path.append(str(Path(__file__).parent.parent))

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
import os
import random
from typing import Any, Dict, Iterator, Optional, Sequence, Tuple

# Add the scripts directory to Python path so imports work from anywhere
sys.path.insert(0, str(Path(__file__).parent))

from seed_catalog_only import seed_catalog
from seed_utils import (
    BulkSeedingContext,
    create_bulk_seeding_context,
    find_free_slot_bulk,
    register_pending_booking,
)
from seed_yaml_loader import SeedDataLoader
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session
import ulid

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.models.address import InstructorServiceArea
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.instructor import BGCConsent, InstructorProfile
from app.models.payment import PlatformCredit, StripeConnectedAccount
from app.models.rbac import Role, UserRole as UserRoleJunction
from app.models.review import Review, ReviewStatus
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.region_boundary_repository import RegionBoundaryRepository
from app.services.timezone_service import TimezoneService
from app.utils.bitset import bits_from_windows, new_empty_bits
from app.utils.time_utils import time_to_minutes


class DatabaseSeeder:
    _INSTRUCTOR_ALLOWED_KEYS = {
        "email",
        "phone",
        "profile",
        "availability_pattern",
        "current_tier_pct",
        "seed_completed_last_30d",
        "seed_randomize_categories",
        "first_name",
        "last_name",
        "zip_code",
        "account_status",
    }
    _PROFILE_ALLOWED_KEYS = {
        "bio",
        "years_experience",
        "services",
    }
    _SERVICE_ALLOWED_KEYS = {
        "name",
        "service_slug",
        "service_catalog_id",
        "description",
        "price",
        "hourly_rate",
        "duration_options",
        "requirements",
        "equipment_required",
        "age_groups",
        "offers_travel",
        "offers_at_location",
        "offers_online",
        "filter_selections",
    }
    _SERVICE_TOKEN_STOPWORDS = {
        "a",
        "an",
        "and",
        "application",
        "at",
        "classes",
        "class",
        "coaching",
        "elementary",
        "for",
        "in",
        "lesson",
        "lessons",
        "of",
        "on",
        "prep",
        "professional",
        "service",
        "services",
        "skills",
        "the",
        "to",
        "training",
        "tutoring",
        "up",
        "various",
        "with",
    }
    _DYNAMIC_MATCH_MIN_SCORE = 0.35

    def __init__(self, db: Optional[Session] = None):
        # Use absolute path based on script location
        seed_data_path = Path(__file__).parent / "seed_data"
        self.loader = SeedDataLoader(seed_data_dir=str(seed_data_path))
        self._external_session = db
        self.engine = db.get_bind() if db is not None else self._create_engine()
        self.created_users = {}
        self.created_services = {}
        self.stripe_mapping = self._load_stripe_mapping()
        self.instructor_seed_plan = {}

    def _create_engine(self):
        db_url = settings.get_database_url()
        # The DatabaseConfig will print which database is being used
        return create_engine(db_url)

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        if self._external_session is not None:
            yield self._external_session
            return
        with Session(self.engine) as session:
            yield session

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

    @classmethod
    def _normalize_seed_text(cls, value: str) -> str:
        text_value = re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower())
        return " ".join(text_value.split())

    @classmethod
    def _tokenize_seed_text(cls, value: str) -> set[str]:
        return {
            token
            for token in cls._normalize_seed_text(value).split()
            if token and token not in cls._SERVICE_TOKEN_STOPWORDS
        }

    @staticmethod
    def _jaccard_similarity(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _audit_instructors_yaml_shape(self, instructors: Sequence[Dict[str, Any]]) -> None:
        """Validate instructors.yaml shape against the current schema contract."""
        instructor_unknown: Counter[str] = Counter()
        profile_unknown: Counter[str] = Counter()
        service_unknown: Counter[str] = Counter()

        for instructor in instructors:
            for key in instructor.keys():
                if key not in self._INSTRUCTOR_ALLOWED_KEYS:
                    instructor_unknown[key] += 1

            profile = instructor.get("profile") or {}
            if not isinstance(profile, dict):
                continue

            for key in profile.keys():
                if key not in self._PROFILE_ALLOWED_KEYS:
                    profile_unknown[key] += 1

            services = profile.get("services") or []
            if not isinstance(services, list):
                continue

            for service in services:
                if not isinstance(service, dict):
                    continue
                for key in service.keys():
                    if key not in self._SERVICE_ALLOWED_KEYS:
                        service_unknown[key] += 1

        print("🔎 Instructors YAML audit:")
        if instructor_unknown:
            print(f"  ⚠️ Unknown instructor-level keys: {dict(instructor_unknown)}")
        if profile_unknown:
            print(f"  ⚠️ Unknown profile-level keys: {dict(profile_unknown)}")
        if service_unknown:
            print(f"  ⚠️ Unknown service-level keys: {dict(service_unknown)}")
        if instructor_unknown or profile_unknown or service_unknown:
            raise ValueError(
                "instructors.yaml contains unsupported keys. "
                "Remove outdated fields and use the current schema contract."
            )

    def _resolve_catalog_service(
        self,
        *,
        service_data: Dict[str, Any],
        instructor_data: Dict[str, Any],
        catalog_services: Sequence[ServiceCatalog],
        catalog_by_id: Dict[str, ServiceCatalog],
        catalog_by_slug: Dict[str, ServiceCatalog],
        catalog_by_name_lc: Dict[str, list[ServiceCatalog]],
        catalog_by_normalized_name: Dict[str, list[ServiceCatalog]],
        min_score: Optional[float] = None,
    ) -> tuple[Optional[ServiceCatalog], str, float]:
        """Resolve a YAML service entry to a ServiceCatalog row with dynamic fallback."""
        explicit_service_id = str(service_data.get("service_catalog_id") or "").strip()
        if explicit_service_id and explicit_service_id in catalog_by_id:
            return catalog_by_id[explicit_service_id], "service_catalog_id", 1.0

        explicit_slug = str(service_data.get("service_slug") or service_data.get("slug") or "").strip().lower()
        if explicit_slug and explicit_slug in catalog_by_slug:
            return catalog_by_slug[explicit_slug], "service_slug", 1.0

        service_name = str(service_data.get("name") or "").strip()
        if not service_name:
            return None, "missing_name", 0.0
        service_name_lc = service_name.lower()
        if service_name_lc in catalog_by_name_lc:
            exact_matches = catalog_by_name_lc[service_name_lc]
            if exact_matches:
                return exact_matches[0], "exact_name", 1.0

        normalized_name = self._normalize_seed_text(service_name)
        if normalized_name and normalized_name in catalog_by_normalized_name:
            normalized_matches = catalog_by_normalized_name[normalized_name]
            if normalized_matches:
                return normalized_matches[0], "normalized_name", 0.95

        profile = instructor_data.get("profile") or {}
        instructor_bio = str(profile.get("bio") or "")
        service_description = str(service_data.get("description") or "")

        name_tokens = self._tokenize_seed_text(service_name)
        detail_tokens = self._tokenize_seed_text(f"{service_name} {service_description}")
        bio_tokens = self._tokenize_seed_text(instructor_bio)
        normalized_service_name = self._normalize_seed_text(service_name)

        best_service: Optional[ServiceCatalog] = None
        best_score = 0.0
        for candidate in catalog_services:
            candidate_name = str(getattr(candidate, "name", "") or "")
            candidate_slug = str(getattr(candidate, "slug", "") or "")
            candidate_tokens = self._tokenize_seed_text(f"{candidate_name} {candidate_slug}")

            name_similarity = max(
                SequenceMatcher(None, normalized_service_name, self._normalize_seed_text(candidate_name)).ratio(),
                SequenceMatcher(None, normalized_service_name, self._normalize_seed_text(candidate_slug)).ratio(),
            )
            token_similarity = self._jaccard_similarity(detail_tokens, candidate_tokens)
            base_name_similarity = self._jaccard_similarity(name_tokens, candidate_tokens)
            bio_similarity = self._jaccard_similarity(bio_tokens, candidate_tokens)

            score = (
                (0.50 * name_similarity)
                + (0.25 * token_similarity)
                + (0.20 * base_name_similarity)
                + (0.05 * bio_similarity)
            )
            if name_tokens & candidate_tokens:
                score += 0.08

            # Strong keyword nudges for common near-matches.
            if "coding" in detail_tokens and "coding" in candidate_tokens:
                score += 0.15
            if "karate" in detail_tokens and "karate" in candidate_tokens:
                score += 0.20
            if "jazz" in detail_tokens and "jazz" in candidate_tokens:
                score += 0.10
            if "esl" in detail_tokens and ("esl" in candidate_tokens or "efl" in candidate_tokens):
                score += 0.12

            if score > best_score:
                best_score = score
                best_service = candidate

        threshold = self._DYNAMIC_MATCH_MIN_SCORE if min_score is None else min_score
        if best_service and best_score >= threshold:
            return best_service, "fuzzy", best_score
        return None, "unresolved", best_score

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

    @staticmethod
    def _resolve_user_timezone(user: Optional[User]) -> str:
        tz_value = getattr(user, "timezone", None) if user else None
        if isinstance(tz_value, str) and tz_value:
            return tz_value
        return TimezoneService.DEFAULT_TIMEZONE

    def _build_booking_timezone_fields(
        self,
        booking_date: date,
        start_time: time,
        end_time: time,
        *,
        instructor_user: Optional[User],
        student_user: Optional[User],
    ) -> Dict[str, Any]:
        instructor_tz = self._resolve_user_timezone(instructor_user)
        student_tz = self._resolve_user_timezone(student_user)
        lesson_tz = TimezoneService.get_lesson_timezone(instructor_tz, is_online=False)
        end_date = booking_date
        if end_time == time(0, 0) and start_time != time(0, 0):
            end_date = booking_date + timedelta(days=1)
        start_utc = TimezoneService.local_to_utc(booking_date, start_time, lesson_tz)
        end_utc = TimezoneService.local_to_utc(end_date, end_time, lesson_tz)
        return {
            "booking_start_utc": start_utc,
            "booking_end_utc": end_utc,
            "lesson_timezone": lesson_tz,
            "instructor_tz_at_booking": instructor_tz,
            "student_tz_at_booking": student_tz,
        }

    def reset_database(self):
        """Clean test data from database"""
        with self._session_scope() as session:
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
                    "DELETE FROM availability_days WHERE instructor_id IN (SELECT id FROM users WHERE email LIKE '%@example.com')"
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

            # Delete filter mappings (reverse FK order)
            result = session.execute(text("DELETE FROM subcategory_filter_options"))
            print(f"    Deleted {result.rowcount} subcategory filter options")
            result = session.execute(text("DELETE FROM subcategory_filters"))
            print(f"    Deleted {result.rowcount} subcategory filters")
            result = session.execute(text("DELETE FROM filter_options"))
            print(f"    Deleted {result.rowcount} filter options")
            result = session.execute(text("DELETE FROM filter_definitions"))
            print(f"    Deleted {result.rowcount} filter definitions")

            # Delete all services from catalog
            result = session.execute(text("DELETE FROM service_catalog"))
            print(f"    Deleted {result.rowcount} catalog services")

            # Delete subcategories then categories
            result = session.execute(text("DELETE FROM service_subcategories"))
            print(f"    Deleted {result.rowcount} service subcategories")
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
        with self._session_scope() as session:
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

        with self._session_scope() as session:
            # Get roles
            admin_role = session.query(Role).filter_by(name=RoleName.ADMIN).first()
            student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()

            if not admin_role or not student_role:
                print("❌ Error: Roles not found. Make sure migrations ran successfully.")
                return

            # Pre-hash password ONCE (bcrypt is expensive ~500ms per hash)
            hashed_password = get_password_hash(password)

            # Pre-load existing users by email for bulk check
            student_emails = [s["email"] for s in students]
            existing_users = {
                u.email: u
                for u in session.query(User).filter(User.email.in_(student_emails)).all()
            }

            created_count = 0
            skipped_existing = 0

            for student_data in students:
                # Determine role based on email
                is_admin = student_data["email"] == "admin@instainstru.com"

                # Use pre-loaded existing users (no query needed)
                existing_user = existing_users.get(student_data["email"])
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
                    hashed_password=hashed_password,  # Use pre-hashed password
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

    def create_instructors(self, *, seed_tier_maintenance: bool = True):
        """Create instructor accounts with profiles and services from YAML"""
        instructors = self.loader.get_instructors()
        self._audit_instructors_yaml_shape(instructors)
        password = self.loader.get_default_password()

        with self._session_scope() as session:
            # Get instructor role
            instructor_role = session.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()

            if not instructor_role:
                print("❌ Error: Instructor role not found. Make sure migrations ran successfully.")
                return

            # Pre-hash password ONCE (bcrypt is expensive ~500ms per hash)
            hashed_password = get_password_hash(password)

            # Pre-load active catalog services and lookup tables once.
            catalog_services = (
                session.query(ServiceCatalog)
                .filter(ServiceCatalog.is_active.is_(True))
                .all()
            )
            catalog_by_id = {svc.id: svc for svc in catalog_services}
            catalog_by_slug = {
                str(svc.slug).strip().lower(): svc
                for svc in catalog_services
                if str(getattr(svc, "slug", "") or "").strip()
            }
            catalog_by_name_lc: Dict[str, list[ServiceCatalog]] = {}
            catalog_by_normalized_name: Dict[str, list[ServiceCatalog]] = {}
            for svc in catalog_services:
                name_lc = str(svc.name).strip().lower()
                if name_lc:
                    catalog_by_name_lc.setdefault(name_lc, []).append(svc)
                normalized_name = self._normalize_seed_text(str(svc.name))
                if normalized_name:
                    catalog_by_normalized_name.setdefault(normalized_name, []).append(svc)

            resolution_stats: Counter[str] = Counter()
            unresolved_service_entries: list[dict[str, Any]] = []

            # PHASE 1: Create all User objects first (for FK constraints)
            user_data_map = {}  # email -> (user_id, user, instructor_data)
            for instructor_data in instructors:
                account_status = instructor_data.get("account_status", "active")
                user_id = str(ulid.ULID())
                user = User(
                    id=user_id,
                    email=instructor_data["email"],
                    first_name=instructor_data["first_name"],
                    last_name=instructor_data["last_name"],
                    phone=instructor_data.get("phone"),
                    zip_code=instructor_data["zip_code"],
                    hashed_password=hashed_password,
                    is_active=True,
                    account_status=account_status,
                )
                session.add(user)
                user_data_map[instructor_data["email"]] = (user_id, user, instructor_data)

            # Flush all users at once (single round trip)
            session.flush()

            # PHASE 2: Create all dependent objects (roles, profiles, services)
            for email, (user_id, user, instructor_data) in user_data_map.items():
                account_status = instructor_data.get("account_status", "active")

                # Assign instructor role
                user_role = UserRoleJunction(user_id=user_id, role_id=instructor_role.id)
                session.add(user_role)

                # Create instructor profile
                profile_data = instructor_data.get("profile", {})
                # Determine seeded onboarding status
                _is_active_account = account_status == "active"
                _now = datetime.now(timezone.utc)

                # Use values as-is from YAML (backend enforces validation at runtime)
                _bio = profile_data.get("bio", "").strip()

                current_tier_pct_value = float(instructor_data.get("current_tier_pct", 15.00))
                seed_completed_last_30d = int(instructor_data.get("seed_completed_last_30d") or 0)
                seed_randomize_categories = bool(instructor_data.get("seed_randomize_categories", False))

                # Pre-generate profile ULID to avoid flush for ID
                profile_id = str(ulid.ULID())
                profile = InstructorProfile(
                    id=profile_id,
                    user_id=user_id,
                    bio=_bio,
                    years_experience=profile_data.get("years_experience", 1),
                    min_advance_booking_hours=2,
                    buffer_time_minutes=0,
                    current_tier_pct=current_tier_pct_value,
                    last_tier_eval_at=_now,
                    # Onboarding defaults for seeded instructors
                    skills_configured=False,
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

                plan_entry = {
                    "user_id": user_id,
                    "profile_id": profile_id,
                    "seed_completed_last_30d": seed_completed_last_30d,
                    "seed_randomize_categories": seed_randomize_categories,
                    "service_ids": [],
                }
                self.instructor_seed_plan[user.email] = plan_entry

                if os.getenv("SEED_FORCE_BGC_PASSED", "1") == "1" and profile.is_live:
                    now_utc = profile.bgc_completed_at or datetime.now(timezone.utc)
                    session.add(
                        BGCConsent(
                            instructor_id=profile_id,
                            consent_version="seed.v1",
                            consented_at=now_utc,
                            ip_address="127.0.0.1",
                        )
                    )

                # Create services from catalog (using dynamic resolver + pre-built lookups)
                service_count = 0
                assigned_catalog_ids: set[str] = set()
                requested_services = profile_data.get("services", []) or []

                for service_data in requested_services:
                    if not isinstance(service_data, dict):
                        continue
                    service_name = str(service_data.get("name") or "").strip()
                    catalog_service, resolution_source, resolution_score = self._resolve_catalog_service(
                        service_data=service_data,
                        instructor_data=instructor_data,
                        catalog_services=catalog_services,
                        catalog_by_id=catalog_by_id,
                        catalog_by_slug=catalog_by_slug,
                        catalog_by_name_lc=catalog_by_name_lc,
                        catalog_by_normalized_name=catalog_by_normalized_name,
                    )
                    resolution_stats[resolution_source] += 1
                    if not catalog_service:
                        unresolved_service_entries.append(
                            {
                                "email": user.email,
                                "service_name": service_name or "<missing>",
                                "score": round(float(resolution_score), 3),
                            }
                        )
                        print(
                            f"  ⚠️  Service '{service_name or '<missing>'}' not found in catalog, skipping "
                            f"(best score={resolution_score:.3f})"
                        )
                        continue
                    if catalog_service.id in assigned_catalog_ids:
                        continue
                    assigned_catalog_ids.add(catalog_service.id)
                    if resolution_source not in {"service_catalog_id", "service_slug", "exact_name"}:
                        print(
                            f"  ℹ️  Mapped '{service_name}' → '{catalog_service.name}' "
                            f"via {resolution_source} (score={resolution_score:.3f})"
                        )

                    # Normalize age_groups to canonical taxonomy values.
                    raw_groups = service_data.get("age_groups") or []
                    normalized_groups = []
                    for g in raw_groups:
                        v = str(g).strip().lower()
                        if v == "both":
                            for val in ("kids", "adults"):
                                if val not in normalized_groups:
                                    normalized_groups.append(val)
                            continue
                        if v in {"kids", "children", "child"}:
                            if "kids" not in normalized_groups:
                                normalized_groups.append("kids")
                            continue
                        if v in {"teen", "teens", "youth"}:
                            if "teens" not in normalized_groups:
                                normalized_groups.append("teens")
                            continue
                        if v in {"toddler", "toddlers", "infant", "infants"}:
                            if "toddler" not in normalized_groups:
                                normalized_groups.append("toddler")
                            continue
                        if v in {"adult", "adults"}:
                            if "adults" not in normalized_groups:
                                normalized_groups.append("adults")
                            continue
                        # drop unknown values

                    # Default to 'adults' when unspecified.
                    if not normalized_groups:
                        normalized_groups = ["adults"]

                    # Keep seeded age groups aligned with catalog eligibility.
                    eligible_groups = [
                        str(v).strip().lower()
                        for v in (getattr(catalog_service, "eligible_age_groups", None) or [])
                        if str(v).strip()
                    ]
                    if eligible_groups:
                        eligible_set = set(eligible_groups)
                        normalized_groups = [g for g in normalized_groups if g in eligible_set]
                        if not normalized_groups:
                            for fallback in ("adults", "kids", "teens", "toddler"):
                                if fallback in eligible_set:
                                    normalized_groups = [fallback]
                                    break

                    # Ensure ~20% of seeded services include kids for testing, when eligible.
                    if eligible_groups and "kids" in eligible_groups:
                        try:
                            import random as _random

                            if ("kids" not in normalized_groups) and (_random.random() < 0.20):
                                normalized_groups.append("kids")
                        except Exception:
                            pass

                    # Use filter selections as provided in YAML.
                    filter_selections = dict(service_data.get("filter_selections") or {})

                    # Create instructor service linked to catalog (pre-generate ULID)
                    hourly_rate = service_data.get("hourly_rate", service_data.get("price"))
                    if hourly_rate is None:
                        print(f"  ⚠️  Service '{service_name}' missing price/hourly_rate, skipping")
                        continue
                    service_id = str(ulid.ULID())
                    offers_travel = bool(service_data.get("offers_travel", False))
                    offers_at_location = bool(service_data.get("offers_at_location", False))
                    offers_online = bool(service_data.get("offers_online", True))
                    if not (offers_travel or offers_at_location or offers_online):
                        offers_online = True
                    service = InstructorService(
                        id=service_id,
                        instructor_profile_id=profile_id,
                        service_catalog_id=catalog_service.id,
                        hourly_rate=hourly_rate,
                        description=service_data.get("description"),
                        duration_options=service_data.get("duration_options", [60]),
                        requirements=service_data.get("requirements"),
                        equipment_required=service_data.get("equipment_required"),
                        age_groups=normalized_groups or None,
                        filter_selections=filter_selections or {},
                        offers_travel=offers_travel,
                        offers_at_location=offers_at_location,
                        offers_online=offers_online,
                        is_active=True,
                    )
                    session.add(service)
                    self.created_services[f"{user.email}:{service_name}"] = service_id
                    service_count += 1
                    plan_entry["service_ids"].append(service_id)

                profile.skills_configured = service_count > 0

                # Create Stripe connected account if mapping exists
                if user.email in self.stripe_mapping and self.stripe_mapping[user.email]:
                    # Don't assume onboarding status - let the app check with Stripe dynamically
                    # This just restores the account association
                    stripe_account = StripeConnectedAccount(
                        id=str(ulid.ULID()),
                        instructor_profile_id=profile_id,
                        stripe_account_id=self.stripe_mapping[user.email],
                        onboarding_completed=True,
                        created_at=_now,
                        updated_at=_now,
                    )
                    session.add(stripe_account)
                    print(f"    💳 Linked to existing Stripe account: {self.stripe_mapping[user.email][:20]}...")

                self.created_users[user.email] = user_id
                status_info = f" [{account_status.upper()}]" if account_status != "active" else ""
                print(
                    f"  ✅ Created instructor: {user.first_name} {user.last_name} with {service_count} services{status_info}"
                )

            if unresolved_service_entries:
                sample_lines = [
                    "  - {email}: '{service_name}' (best_score={score})".format(
                        email=row["email"],
                        service_name=row["service_name"],
                        score=row["score"],
                    )
                    for row in unresolved_service_entries[:20]
                ]
                raise ValueError(
                    "instructors.yaml contains services that do not exist in the current catalog.\n"
                    + "\n".join(sample_lines)
                )

            if seed_tier_maintenance:
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
        if resolution_stats:
            print(f"🔁 Service resolution stats: {dict(resolution_stats)}")

    def seed_tier_maintenance_sessions(self, reason: str = "") -> int:
        """Seed tier maintenance sessions using a fresh session."""
        with self._session_scope() as session:
            return self._seed_tier_maintenance_sessions(session, reason=reason)

    def _slot_conflicts(
        self,
        session: Session,
        user_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        pending_spans: set[tuple[str, date, time, time]],
        *,
        check_instructor: bool = False,
    ) -> bool:
        """Check for overlapping bookings for a user (student or instructor).

        Args:
            user_id: The student or instructor ID to check
            booking_date: Date of the proposed booking
            start_time: Start time of the proposed booking
            end_time: End time of the proposed booking
            pending_spans: Set of (user_id, date, start, end) tuples already queued
            check_instructor: If True, check instructor_id column; else student_id
        """
        # Check against pending (not yet flushed) bookings
        for uid, dt, st, et in pending_spans:
            if uid == user_id and dt == booking_date:
                # Overlap if start < other_end AND end > other_start
                if start_time < et and end_time > st:
                    return True

        # Check against committed bookings in the database
        id_column = "instructor_id" if check_instructor else "student_id"
        overlap_sql = text(
            f"""
            SELECT 1
            FROM bookings
            WHERE {id_column} = :user_id
              AND booking_date = :booking_date
              AND start_time < :end_time
              AND end_time > :start_time
            LIMIT 1
            """  # nosec B608 - id_column is hardcoded, not user input
        )
        with session.no_autoflush:
            overlap = session.execute(
                overlap_sql,
                {
                    "user_id": user_id,
                    "booking_date": booking_date,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            ).scalar()
        return bool(overlap)

    def _seed_tier_maintenance_sessions(self, session: Session, reason: str = "") -> int:
        """Seed completed sessions in the last 30 days to preserve tier assignments."""

        if not self.instructor_seed_plan:
            print("  ℹ️  Skipping tier maintenance seeding: instructor seed plan not initialized")
            return 0

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=30)

        student_role = session.query(Role).filter_by(name=RoleName.STUDENT).first()
        if not student_role:
            print("  ⚠️  Skipping tier maintenance seeding: student role not present")
            return 0

        students = (
            session.query(User)
            .join(UserRoleJunction, UserRoleJunction.user_id == User.id)
            .filter(UserRoleJunction.role_id == student_role.id, User.email.like("%@example.com"))
            .all()
        )

        if not students:
            include_flag = os.getenv("INCLUDE_MOCK_USERS", "")
            gate_hint = ""
            if include_flag.lower() in {"0", "false", "no"}:
                gate_hint = "mock student seeding disabled (INCLUDE_MOCK_USERS=0)"
            elif reason:
                gate_hint = reason
            else:
                gate_hint = "no mock students available"
            print(f"  ⚠️  Skipping tier maintenance seeding: {gate_hint}")
            return 0

        instructor_ids = [
            plan.get("user_id")
            for plan in self.instructor_seed_plan.values()
            if plan.get("user_id")
        ]
        instructors_by_id: Dict[str, User] = {}
        if instructor_ids:
            instructors_by_id = {
                instructor.id: instructor
                for instructor in session.query(User).filter(User.id.in_(instructor_ids)).all()
            }

        rng = random.Random(42)
        total_seeded = 0
        pending_student_spans: set[tuple[str, date, time, time]] = set()
        pending_instructor_spans: set[tuple[str, date, time, time]] = set()
        skipped_conflicts = 0
        max_attempts_per_booking = 8

        for email, plan in self.instructor_seed_plan.items():
            desired = int(plan.get("seed_completed_last_30d") or 0)
            if desired <= 0:
                continue

            user_id = plan.get("user_id")
            if not user_id:
                continue
            instructor_user = instructors_by_id.get(user_id)

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
                inserted = False
                for _attempt in range(max_attempts_per_booking):
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
                    start_dt_naive = datetime.combine(booking_date, start_time)  # tz-pattern-ok: seed script generates test data
                    end_dt_naive = start_dt_naive + timedelta(minutes=duration)
                    end_time = end_dt_naive.time()

                    start_dt = start_dt_naive.replace(tzinfo=timezone.utc)
                    end_dt = end_dt_naive.replace(tzinfo=timezone.utc)

                    is_remote = bool(getattr(service, "offers_online", False))
                    location_type = "online" if is_remote else "student_location"
                    meeting_location = "Online" if is_remote else "Student location"

                    student = rng.choice(students)

                    # Check for instructor overlap first (most common conflict)
                    if self._slot_conflicts(
                        session,
                        user_id,
                        booking_date,
                        start_time,
                        end_time,
                        pending_instructor_spans,
                        check_instructor=True,
                    ):
                        continue

                    # Check for student overlap
                    if self._slot_conflicts(
                        session,
                        student.id,
                        booking_date,
                        start_time,
                        end_time,
                        pending_student_spans,
                        check_instructor=False,
                    ):
                        continue

                    hourly_rate = Decimal(str(service.hourly_rate)).quantize(Decimal("0.01"))
                    total_price = (hourly_rate * Decimal(duration) / Decimal(60)).quantize(Decimal("0.01"))

                    service_name = (
                        service.catalog_entry.name
                        if service.catalog_entry
                        else (service.description or service.name)
                    )

                    tz_fields = self._build_booking_timezone_fields(
                        booking_date,
                        start_time,
                        end_time,
                        instructor_user=instructor_user,
                        student_user=student,
                    )
                    booking = Booking(
                        student_id=student.id,
                        instructor_id=user_id,
                        instructor_service_id=service.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        **tz_fields,
                        duration_minutes=duration,
                        service_name=service_name,
                        hourly_rate=hourly_rate,
                        total_price=total_price,
                        status=BookingStatus.COMPLETED,
                        location_type=location_type,
                        meeting_location=meeting_location,
                        location_address=meeting_location,
                        service_area=None,
                        student_note="Seeded maintenance session",
                        created_at=start_dt - timedelta(days=1),
                        confirmed_at=start_dt - timedelta(hours=2),
                        completed_at=end_dt,
                    )
                    session.add(booking)
                    pending_student_spans.add((student.id, booking_date, start_time, end_time))
                    pending_instructor_spans.add((user_id, booking_date, start_time, end_time))
                    total_seeded += 1
                    inserted = True
                    break

                if not inserted:
                    skipped_conflicts += 1

        if total_seeded:
            print(f"  🎯 Seeded {total_seeded} maintenance sessions to preserve tier assignments")
        else:
            print("  ℹ️  Tier maintenance seeding skipped: existing completed sessions already satisfy targets")
        if skipped_conflicts:
            print(
                f"  ⚠️  Tier maintenance skipped {skipped_conflicts} attempt(s) due to slot conflicts"
            )
        return total_seeded

    def create_coverage_areas(self):
        """Assign deterministic primary/secondary/by_request neighborhoods using repository pattern.

        Coverage rules are defined in seed_data/coverage.yaml, allowing per-instructor overrides
        by email, and default Manhattan neighborhoods otherwise.
        """
        with self._session_scope() as session:
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

            # Pre-load all instructors with roles in ONE query
            instructor_emails = [e for e in self.created_users.keys() if e.endswith("@example.com")]
            instructor_user_ids = [self.created_users[e] for e in instructor_emails]
            instructors_with_roles = (
                session.query(User)
                .filter(User.id.in_(instructor_user_ids))
                .all()
            )
            instructor_id_set = {
                u.id for u in instructors_with_roles
                if any(r.name == RoleName.INSTRUCTOR for r in u.roles)
            }

            # Pre-load all existing service areas in ONE query
            existing_areas = (
                session.query(InstructorServiceArea)
                .filter(InstructorServiceArea.instructor_id.in_(list(instructor_id_set)))
                .all()
            )
            existing_lookup = {
                (a.instructor_id, a.neighborhood_id): a for a in existing_areas
            }

            # Assign to each instructor (no per-user queries needed)
            for email, user_id in self.created_users.items():
                if not email.endswith("@example.com"):
                    continue
                if user_id not in instructor_id_set:
                    continue

                # Pick config: override by email, else defaults
                cfg = overrides.get(email, defaults)
                for item in cfg.get("names", []):
                    rid = name_to_id.get(item["name"]) if item.get("name") else None
                    if not rid:
                        continue

                    # Upsert using pre-loaded data (no query per area)
                    key = (user_id, rid)
                    existing = existing_lookup.get(key)
                    if existing:
                        existing.is_active = True
                        if item.get("coverage_type"):
                            existing.coverage_type = item.get("coverage_type")
                        existing.max_distance_miles = float(cfg.get("max_distance_miles", 2.0))
                    else:
                        area = InstructorServiceArea(
                            instructor_id=user_id,
                            neighborhood_id=rid,
                            coverage_type=item.get("coverage_type"),
                            max_distance_miles=float(cfg.get("max_distance_miles", 2.0)),
                            is_active=True,
                        )
                        session.add(area)
                        existing_lookup[key] = area

            session.flush()
            session.commit()
            print("✅ Assigned instructor coverage areas from YAML rules")

    def create_availability(self):
        """Create availability slots based on patterns (optimized with bulk operations)."""
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

        print(f"  ⏳ Creating availability for {len(instructors)} instructors ({weeks_past} past + {weeks_future} future weeks)...")

        with self._session_scope() as session:
            repo = AvailabilityDayRepository(session)
            created_count = 0

            # Collect ALL items for ALL instructors first
            all_items: list[Tuple[str, date, bytes]] = []

            for instructor_data in instructors:
                pattern_name = instructor_data.get("availability_pattern")
                if not pattern_name:
                    continue

                pattern = self.loader.get_availability_pattern(pattern_name)
                if not pattern:
                    continue

                user_id = self.created_users.get(instructor_data["email"])
                if not user_id:
                    continue

                days_data = pattern.get("days", {})

                # Build items for all weeks for this instructor
                for week_offset in range(-weeks_past, weeks_future + 1):
                    week_start_date = self._get_week_start_for_offset(week_offset)
                    day_windows: Dict[date, list[Tuple[str, str]]] = {}

                    for day_name, time_slots in days_data.items():
                        target_date = self._get_date_for_day(day_name, week_offset)
                        normalized_slots: list[Tuple[str, str]] = []
                        for start_str, end_str in time_slots:
                            start_formatted = f"{start_str}:00" if len(start_str) == 5 else start_str
                            end_formatted = f"{end_str}:00" if len(end_str) == 5 else end_str
                            normalized_slots.append((start_formatted, end_formatted))
                        if normalized_slots:
                            day_windows.setdefault(target_date, []).extend(normalized_slots)

                    for offset in range(7):
                        day_date = week_start_date + timedelta(days=offset)
                        windows = day_windows.get(day_date, [])
                        bits = bits_from_windows(windows) if windows else new_empty_bits()
                        all_items.append((user_id, day_date, bits))

                created_count += 1

            # Single native PostgreSQL UPSERT for all instructors (1 statement)
            if all_items:
                repo.bulk_upsert_native(all_items)
                session.commit()

        print(f"  ✅ Created availability patterns for {created_count} instructors")

    def _get_week_start_for_offset(self, week_offset: int) -> date:
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        return start_of_week + timedelta(weeks=week_offset)

    def _get_date_for_day(self, day_name: str, week_offset: int) -> date:
        """Return the calendar date for a given day name within the week offset."""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        day_index = days.index(day_name.lower())

        target_week_start = self._get_week_start_for_offset(week_offset)
        return target_week_start + timedelta(days=day_index)

    def _day_name_to_number(self, day_name):
        """Convert day name to number (0=Monday, 6=Sunday)"""
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return days.index(day_name.lower())

    def _prepare_bitmap_environment(self):
        if os.getenv("BITMAP_PIPELINE_COMPLETED") == "1":
            print("  ℹ️  Bitmap pipeline already executed earlier in this run; skipping local seed/backfill.")
            return
        flag = os.getenv("SEED_AVAILABILITY", "0").lower() in {"1", "true", "yes"}
        if not flag:
            return

        weeks = self._get_env_int("SEED_AVAILABILITY_WEEKS", 3)
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

        with self._session_scope() as session:
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
        utc_today = datetime.now(timezone.utc).date()
        window_start = utc_today - timedelta(days=lookback_days)
        window_end = utc_today + timedelta(days=horizon_days)

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
        """Create sample bookings for testing (optimized with bulk loading)."""
        settings_cfg = self.loader.config.get("settings", {})
        booking_days_future = settings_cfg.get("booking_days_future", settings_cfg.get("booking_days_ahead", 7))
        booking_days_past = settings_cfg.get("booking_days_past", 21)

        with self._session_scope() as session:
            # Get all students
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

            # Build list of instructors with their services (pre-load in bulk)
            instructor_emails = [e for e in self.created_users.keys() if e.endswith("@example.com")]
            instructor_user_ids = [self.created_users[e] for e in instructor_emails]

            # Pre-load all instructor users with roles in ONE query
            instructors = (
                session.query(User)
                .filter(User.id.in_(instructor_user_ids))
                .all()
            )
            instructors_by_id = {instructor.id: instructor for instructor in instructors}
            instructor_id_set = {
                u.id for u in instructors
                if any(r.name == RoleName.INSTRUCTOR for r in u.roles)
            }

            # Pre-load all services for all instructors in ONE query
            all_services = (
                session.query(InstructorService)
                .join(InstructorProfile)
                .filter(InstructorProfile.user_id.in_(list(instructor_id_set)))
                .all()
            )

            # Group services by instructor user_id
            services_by_instructor: Dict[str, list[InstructorService]] = {}
            for svc in all_services:
                # Get user_id from profile
                user_id = svc.instructor_profile.user_id
                if user_id not in services_by_instructor:
                    services_by_instructor[user_id] = []
                services_by_instructor[user_id].append(svc)

            instructor_data_list = [
                (uid, services_by_instructor[uid])
                for uid in instructor_id_set
                if uid in services_by_instructor and services_by_instructor[uid]
            ]

            if not instructor_data_list:
                print("  ⚠️  No instructors with services found")
                return 0

            # Pre-load all data for bulk operations
            instructor_ids = [inst_id for inst_id, _ in instructor_data_list]
            student_ids = [s.id for s in students]
            print(f"  ⏳ Pre-loading bitmap data for {len(instructor_ids)} instructors...")

            bulk_ctx = create_bulk_seeding_context(
                session,
                instructor_ids=instructor_ids,
                student_ids=student_ids,
                lookback_days=booking_days_past,  # Include past for historical booking overlap detection
                horizon_days=booking_days_future + 7,
            )

            # Pre-fetch service catalog names
            catalog_services = {
                cs.id: cs.name
                for cs in session.query(ServiceCatalog.id, ServiceCatalog.name).all()
            }

            booking_count = 0
            conversation_pairs: set[tuple[str, str]] = set()  # Track (student_id, instructor_id) pairs

            # Create 1-3 bookings per instructor using bulk slot finding
            for instructor_id, services in instructor_data_list:
                instructor_user = instructors_by_id.get(instructor_id)
                num_bookings = random.randint(1, min(3, len(students)))

                for _ in range(num_bookings):
                    service = random.choice(services)
                    student = random.choice(students)
                    duration = random.choice(service.duration_options)

                    slot = find_free_slot_bulk(
                        bulk_ctx,
                        instructor_id=instructor_id,
                        student_id=student.id,
                        base_date=date.today(),
                        lookback_days=0,
                        horizon_days=booking_days_future,
                        durations_minutes=[duration],
                    )

                    if not slot:
                        continue

                    booking_date, start_time, end_time = slot
                    service_name = catalog_services.get(service.service_catalog_id, "Service")

                    tz_fields = self._build_booking_timezone_fields(
                        booking_date,
                        start_time,
                        end_time,
                        instructor_user=instructor_user,
                        student_user=student,
                    )
                    booking = Booking(
                        student_id=student.id,
                        instructor_id=instructor_id,
                        instructor_service_id=service.id,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                        **tz_fields,
                        duration_minutes=duration,
                        service_name=service_name,
                        hourly_rate=service.hourly_rate,
                        total_price=float(service.hourly_rate) * (duration / 60),
                        status=BookingStatus.CONFIRMED,
                        service_area=None,
                        meeting_location="Online",
                        location_address="Online",
                        location_type="neutral_location",
                    )
                    session.add(booking)

                    # Register in context for conflict detection
                    register_pending_booking(
                        bulk_ctx, instructor_id, student.id, booking_date, start_time, end_time
                    )
                    booking_count += 1
                    conversation_pairs.add((student.id, instructor_id))

            session.commit()

            # Create conversations for all booking pairs
            if conversation_pairs:
                conv_repo = ConversationRepository(db=session)
                conv_count = 0
                for student_id, instructor_id in conversation_pairs:
                    _, created = conv_repo.get_or_create(
                        student_id=student_id,
                        instructor_id=instructor_id,
                    )
                    if created:
                        conv_count += 1
                session.commit()
                if conv_count:
                    print(f"  💬 Created {conv_count} conversations for bookings")

            # Create historical bookings using the same bulk context
            self._create_historical_bookings_bulk(session, bulk_ctx, booking_days_past)
            self._create_completed_bookings_bulk(session, bulk_ctx, booking_days_past)

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
                end_time = (
                    datetime.combine(  # tz-pattern-ok: seed script generates test data
                        date.today(), start_time
                    )
                    + timedelta(minutes=duration)
                ).time()

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

                tz_fields = self._build_booking_timezone_fields(
                    booking_date,
                    start_time,
                    end_time,
                    instructor_user=instructor,
                    student_user=student,
                )
                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor.id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    **tz_fields,
                    status=BookingStatus.COMPLETED,
                    location_type="neutral_location",
                    meeting_location="Zoom",
                    location_address="Zoom",
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
                end_time = (
                    datetime.combine(  # tz-pattern-ok: seed script generates test data
                        date.today(), start_time
                    )
                    + timedelta(minutes=duration)
                ).time()

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

                tz_fields = self._build_booking_timezone_fields(
                    booking_date,
                    start_time,
                    end_time,
                    instructor_user=instructor,
                    student_user=student,
                )
                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor.id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    **tz_fields,
                    status=BookingStatus.COMPLETED,
                    location_type="neutral_location",
                    meeting_location="In-person",
                    location_address="In-person",
                    service_name=catalog_service.name if catalog_service else "Service",
                    service_area="Manhattan",
                    hourly_rate=service.hourly_rate,
                    total_price=float(service.hourly_rate) * (duration / 60),
                    duration_minutes=duration,
                    student_note="Completed lesson for testing Book Again feature",
                    completed_at=datetime.now() - timedelta(days=days_ago - 1),  # Mark as completed day after booking
                )
                session.add(booking)
                completed_count += 1

        session.commit()
        if completed_count > 0:
            print(f"  🎯 Created {completed_count} completed bookings for active students (Book Again testing)")

    def _create_historical_bookings_bulk(
        self, session: Session, bulk_ctx: BulkSeedingContext, booking_days_past: int
    ) -> None:
        """Create past bookings for suspended/deactivated instructors (bulk optimized)."""
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
            services = (
                session.query(InstructorService)
                .join(InstructorProfile)
                .filter(InstructorProfile.user_id == instructor.id)
                .all()
            )

            if not services:
                continue

            num_past_bookings = random.randint(2, 3)
            for i in range(num_past_bookings):
                service = random.choice(services)
                student = random.choice(students)
                duration = random.choice(service.duration_options)

                days_ago = random.randint(7, max(7, booking_days_past))
                booking_date = date.today() - timedelta(days=days_ago)

                hour = random.randint(10, 17)
                start_time = time(hour, 0)
                end_time = (
                    datetime.combine(  # tz-pattern-ok: seed script generates test data
                        date.today(), start_time
                    )
                    + timedelta(minutes=duration)
                ).time()

                # In-memory conflict check
                start_min = time_to_minutes(start_time, is_end_time=False)
                end_min = time_to_minutes(end_time, is_end_time=True)

                # Check for conflicts in context
                has_conflict = False
                for key in list(bulk_ctx.pending_instructor_bookings) + list(bulk_ctx.instructor_bookings):
                    if key[0] == instructor.id and key[1] == booking_date:
                        if start_min < key[3] and end_min > key[2]:
                            has_conflict = True
                            break

                if not has_conflict:
                    for key in list(bulk_ctx.pending_student_bookings) + list(bulk_ctx.student_bookings):
                        if key[0] == student.id and key[1] == booking_date:
                            if start_min < key[3] and end_min > key[2]:
                                has_conflict = True
                                break

                if has_conflict:
                    continue

                tz_fields = self._build_booking_timezone_fields(
                    booking_date,
                    start_time,
                    end_time,
                    instructor_user=instructor,
                    student_user=student,
                )
                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor.id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    **tz_fields,
                    status=BookingStatus.COMPLETED,
                    location_type="neutral_location",
                    meeting_location="Zoom",
                    location_address="Zoom",
                    service_name=service.catalog_entry.name if service.catalog_entry else "Service",
                    service_area=None,
                    hourly_rate=service.hourly_rate,
                    total_price=service.session_price(duration),
                    duration_minutes=duration,
                    student_note=f"Historical booking for testing - {instructor.account_status} instructor",
                )
                session.add(booking)
                register_pending_booking(bulk_ctx, instructor.id, student.id, booking_date, start_time, end_time)
                historical_count += 1

        session.commit()
        if historical_count > 0:
            print(f"  📚 Created {historical_count} historical bookings for inactive instructors")

    def _create_completed_bookings_bulk(
        self, session: Session, bulk_ctx: BulkSeedingContext, booking_days_past: int
    ) -> None:
        """Create completed bookings for active students (bulk optimized)."""
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

        # Pre-fetch service catalog names
        catalog_services = {
            cs.id: cs.name
            for cs in session.query(ServiceCatalog.id, ServiceCatalog.name).all()
        }

        for student in active_students:
            num_completed = random.randint(2, 3)

            for _ in range(num_completed):
                instructor = random.choice(active_instructors)

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

                days_ago = random.randint(7, max(7, booking_days_past))
                booking_date = date.today() - timedelta(days=days_ago)

                hour = random.randint(10, 17)
                start_time = time(hour, 0)
                end_time = (
                    datetime.combine(  # tz-pattern-ok: seed script generates test data
                        date.today(), start_time
                    )
                    + timedelta(minutes=duration)
                ).time()

                # In-memory conflict check
                start_min = time_to_minutes(start_time, is_end_time=False)
                end_min = time_to_minutes(end_time, is_end_time=True)

                has_conflict = False
                for key in list(bulk_ctx.pending_instructor_bookings) + list(bulk_ctx.instructor_bookings):
                    if key[0] == instructor.id and key[1] == booking_date:
                        if start_min < key[3] and end_min > key[2]:
                            has_conflict = True
                            break

                if not has_conflict:
                    for key in list(bulk_ctx.pending_student_bookings) + list(bulk_ctx.student_bookings):
                        if key[0] == student.id and key[1] == booking_date:
                            if start_min < key[3] and end_min > key[2]:
                                has_conflict = True
                                break

                if has_conflict:
                    continue

                service_name = catalog_services.get(service.service_catalog_id, "Service")

                tz_fields = self._build_booking_timezone_fields(
                    booking_date,
                    start_time,
                    end_time,
                    instructor_user=instructor,
                    student_user=student,
                )
                booking = Booking(
                    student_id=student.id,
                    instructor_id=instructor.id,
                    instructor_service_id=service.id,
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    **tz_fields,
                    status=BookingStatus.COMPLETED,
                    location_type="neutral_location",
                    meeting_location="In-person",
                    location_address="In-person",
                    service_name=service_name,
                    service_area="Manhattan",
                    hourly_rate=service.hourly_rate,
                    total_price=float(service.hourly_rate) * (duration / 60),
                    duration_minutes=duration,
                    student_note="Completed lesson for testing Book Again feature",
                    completed_at=datetime.now() - timedelta(days=days_ago - 1),
                )
                session.add(booking)
                register_pending_booking(bulk_ctx, instructor.id, student.id, booking_date, start_time, end_time)
                completed_count += 1

        session.commit()
        if completed_count > 0:
            print(f"  🎯 Created {completed_count} completed bookings for active students (Book Again testing)")

    def create_reviews(self, strict: bool = False) -> int:
        """Create 3 published reviews per active instructor to enable ratings display.

        Uses bulk loading optimization: pre-fetches all bitmap data and bookings
        in 2 queries, then does in-memory conflict detection. Uses SQLAlchemy
        bulk INSERT for bookings and reviews (2 round trips instead of ~200).
        """

        with self._session_scope() as session:
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
                utc_today = datetime.now(timezone.utc).date()

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
                        "Run: SEED_AVAILABILITY=1 ... prep_db.py --seed-all"
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

                # Get all students for random assignment
                all_students = (
                    session.query(User)
                    .join(UserRoleJunction)
                    .filter(
                        UserRoleJunction.role_id == student_role.id,
                        User.email.like("%@example.com"),
                        User.account_status == "active",
                    )
                    .all()
                )
                if not all_students:
                    print("  ⚠️  No students found; skipping review seeding")
                    return 0

                student_ids = [s.id for s in all_students]

                # Pre-load all instructor services
                all_services_by_instructor: Dict[str, list] = {}
                for instructor in active_instructors:
                    services = (
                        session.query(InstructorService)
                        .join(InstructorProfile)
                        .filter(InstructorProfile.user_id == instructor.id)
                        .all()
                    )
                    if services:
                        all_services_by_instructor[instructor.id] = services

                # Get existing completed bookings for all instructors
                existing_completed_bookings: Dict[str, list] = {inst.id: [] for inst in active_instructors}
                all_completed = (
                    session.query(Booking)
                    .filter(
                        Booking.instructor_id.in_(instructor_ids),
                        Booking.status == BookingStatus.COMPLETED,
                    )
                    .order_by(Booking.booking_date.desc())
                    .all()
                )
                for booking in all_completed:
                    existing_completed_bookings[booking.instructor_id].append(booking)

                # Get existing review booking IDs
                existing_review_booking_ids = set(
                    r[0]
                    for r in session.query(Review.booking_id)
                    .filter(Review.instructor_id.in_(instructor_ids))
                    .all()
                )

                # =========================================================
                # BULK LOADING OPTIMIZATION
                # Pre-fetch all bitmap data and bookings in 2 queries
                # =========================================================
                print("  ⏳ Pre-loading bitmap data and bookings for bulk processing...")
                bulk_ctx = create_bulk_seeding_context(
                    session,
                    instructor_ids=instructor_ids,
                    student_ids=student_ids,
                    lookback_days=seed_lookback,
                    horizon_days=seed_horizon,
                )
                print(f"  ✓ Loaded {len(bulk_ctx.bitmap_data)} bitmap rows, "
                      f"{len(bulk_ctx.instructor_bookings)} booking spans")

                # =========================================================
                # BULK INSERT OPTIMIZATION
                # Collect all data in memory, then bulk INSERT at end
                # =========================================================
                pending_bookings: list[tuple] = []  # Booking data tuples
                pending_reviews: list[tuple] = []   # Review data tuples
                # Track booking_id -> booking_data for reviews
                booking_id_map: Dict[str, dict] = {}

                for instructor in active_instructors:
                    # Get existing completed bookings (real ORM objects)
                    existing_for_instructor = existing_completed_bookings.get(instructor.id, [])[:]
                    # Track how many we need to create
                    needed = 3 - len(existing_for_instructor)

                    # Create synthetic bookings if needed (up to 3 total)
                    new_booking_ids = []
                    for _ in range(max(0, needed)):
                        services = all_services_by_instructor.get(instructor.id)
                        if not services:
                            break

                        student = preferred_student if preferred_student else random.choice(all_students)

                        service = random.choice(services)
                        duration = random.choice(service.duration_options)
                        max_days_ago = max(7, seed_lookback - 1)
                        days_ago = random.randint(7, max_days_ago)
                        base_date_val = utc_today - timedelta(days=days_ago)
                        helper_completed_at = datetime.now(timezone.utc) - timedelta(days=days_ago - 1)

                        # Use bulk slot finding (in-memory conflict detection)
                        slot = find_free_slot_bulk(
                            bulk_ctx,
                            instructor_id=instructor.id,
                            student_id=student.id,
                            base_date=base_date_val,
                            lookback_days=seed_lookback,
                            horizon_days=0,
                            day_start_hour=seed_day_start,
                            day_end_hour=seed_day_end,
                            step_minutes=seed_step_minutes,
                            durations_minutes=seed_durations,
                            randomize=True,
                            past_only=True,
                        )

                        if not slot:
                            break

                        booking_date_val, start_time_val, end_time_val = slot
                        if booking_date_val > utc_today:
                            print(
                                f"WARNING: Skipping future date {booking_date_val} for completed review booking."
                            )
                            continue

                        # Pre-generate ULID for bulk insert
                        booking_id = str(ulid.ULID())
                        service_name = service.catalog_entry.name if service.catalog_entry else "Service"
                        total_price = float(service.hourly_rate) * (duration / 60)

                        tz_fields = self._build_booking_timezone_fields(
                            booking_date_val,
                            start_time_val,
                            end_time_val,
                            instructor_user=instructor,
                            student_user=student,
                        )

                        # Collect booking data for bulk INSERT
                        pending_bookings.append({
                            "id": booking_id,
                            "student_id": student.id,
                            "instructor_id": instructor.id,
                            "instructor_service_id": service.id,
                            "booking_date": booking_date_val,
                            "start_time": start_time_val,
                            "end_time": end_time_val,
                            "booking_start_utc": tz_fields["booking_start_utc"],
                            "booking_end_utc": tz_fields["booking_end_utc"],
                            "lesson_timezone": tz_fields["lesson_timezone"],
                            "instructor_tz_at_booking": tz_fields["instructor_tz_at_booking"],
                            "student_tz_at_booking": tz_fields["student_tz_at_booking"],
                            "service_name": service_name,
                            "hourly_rate": float(service.hourly_rate),
                            "total_price": total_price,
                            "duration_minutes": duration,
                            "status": BookingStatus.COMPLETED.value,
                            "location_type": "neutral_location",
                            "meeting_location": "In-person",
                            "student_note": "Seeded completed booking for reviews",
                            "completed_at": helper_completed_at,
                        })

                        # Track for review creation
                        booking_id_map[booking_id] = {
                            "student_id": student.id,
                            "instructor_id": instructor.id,
                            "instructor_service_id": service.id,
                            "completed_at": helper_completed_at,
                        }
                        new_booking_ids.append(booking_id)

                        # Register in context for subsequent conflict detection
                        register_pending_booking(bulk_ctx, instructor.id, student.id,
                                                booking_date_val, start_time_val, end_time_val)

                    # Collect reviews for existing + new bookings (up to 3)
                    # First, handle existing bookings
                    for booking in existing_for_instructor[:3]:
                        if booking.id in existing_review_booking_ids:
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

                        pending_reviews.append({
                            "id": str(ulid.ULID()),
                            "booking_id": booking.id,
                            "student_id": booking.student_id,
                            "instructor_id": booking.instructor_id,
                            "instructor_service_id": booking.instructor_service_id,
                            "rating": rating_value,
                            "review_text": review_text,
                            "status": ReviewStatus.PUBLISHED.value,
                            "is_verified": True,
                            "booking_completed_at": completed_at,
                        })
                        existing_review_booking_ids.add(booking.id)

                    # Then, handle new bookings (up to remaining slots)
                    remaining_slots = 3 - len(existing_for_instructor)
                    for booking_id in new_booking_ids[:remaining_slots]:
                        if booking_id in existing_review_booking_ids:
                            continue

                        bdata = booking_id_map[booking_id]
                        rating_value = random.choices([5, 4, 3], weights=[60, 30, 10])[0]
                        sample_texts = [
                            "Great lesson, very helpful and patient.",
                            "Clear explanations and good pace.",
                            "Enjoyable session; learned a lot.",
                            "Professional and friendly instructor.",
                            "Challenging but rewarding lesson.",
                        ]
                        review_text = random.choice(sample_texts)

                        pending_reviews.append({
                            "id": str(ulid.ULID()),
                            "booking_id": booking_id,
                            "student_id": bdata["student_id"],
                            "instructor_id": bdata["instructor_id"],
                            "instructor_service_id": bdata["instructor_service_id"],
                            "rating": rating_value,
                            "review_text": review_text,
                            "status": ReviewStatus.PUBLISHED.value,
                            "is_verified": True,
                            "booking_completed_at": bdata["completed_at"],
                        })
                        existing_review_booking_ids.add(booking_id)

                # =========================================================
                # EXECUTE BULK INSERTS (2 round trips total)
                # =========================================================

                # Bulk INSERT bookings
                if pending_bookings:
                    print(f"  ⏳ Bulk inserting {len(pending_bookings)} bookings...")
                    booking_sql = text("""
                        INSERT INTO bookings (
                            id, student_id, instructor_id, instructor_service_id,
                            booking_date, start_time, end_time,
                            booking_start_utc, booking_end_utc, lesson_timezone,
                            instructor_tz_at_booking, student_tz_at_booking,
                            service_name, hourly_rate, total_price, duration_minutes,
                            status, location_type, meeting_location, student_note, completed_at,
                            created_at, confirmed_at
                        ) VALUES (
                            :id, :student_id, :instructor_id, :instructor_service_id,
                            :booking_date, :start_time, :end_time,
                            :booking_start_utc, :booking_end_utc, :lesson_timezone,
                            :instructor_tz_at_booking, :student_tz_at_booking,
                            :service_name, :hourly_rate, :total_price, :duration_minutes,
                            :status, :location_type, :meeting_location, :student_note, :completed_at,
                            NOW(), NOW()
                        )
                    """)
                    session.execute(booking_sql, pending_bookings)

                # Bulk INSERT reviews
                if pending_reviews:
                    print(f"  ⏳ Bulk inserting {len(pending_reviews)} reviews...")
                    review_sql = text("""
                        INSERT INTO reviews (
                            id, booking_id, student_id, instructor_id, instructor_service_id,
                            rating, review_text, status, is_verified, booking_completed_at,
                            created_at, updated_at
                        ) VALUES (
                            :id, :booking_id, :student_id, :instructor_id, :instructor_service_id,
                            :rating, :review_text, :status, :is_verified, :booking_completed_at,
                            NOW(), NOW()
                        )
                    """)
                    session.execute(review_sql, pending_reviews)

                session.commit()
                print(f"✅ Seeded {len(pending_reviews)} published reviews for active instructors")
                if pending_bookings:
                    print(f"  ↪︎ Created {len(pending_bookings)} synthetic completed bookings for reviews")
                return len(pending_reviews)
            except Exception as e:
                session.rollback()
                print(f"  ⚠️  Skipped review seeding due to error: {e}")
                if strict:
                    raise
                return 0

    def print_summary(self):
        """Print summary of created data"""
        with self._session_scope() as session:
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

        with self._session_scope() as session:
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
