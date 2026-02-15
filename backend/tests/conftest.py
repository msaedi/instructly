# backend/tests/conftest.py
"""
Pytest configuration file with PRODUCTION DATABASE PROTECTION.
This file is automatically loaded by pytest and sets up the test environment.

CRITICAL: This file now includes safety checks to prevent accidental
production database usage during tests.

UPDATED FOR WORK STREAM #10: Bitmap-only availability design.
All fixtures now create availability using AvailabilityDayRepository and bitmap windows.
"""

# Register shared fixtures from tests/fixtures/
pytest_plugins = [
    "tests.fixtures.taxonomy_fixtures",
]

# Fallback in case this file is run in isolation or a different rootdir is inferred
try:
    import backend  # noqa: F401
except ModuleNotFoundError:
    from pathlib import Path
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[2]  # <repo>/
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

import asyncio
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import importlib
import json
import os
import secrets
import sys
import threading
from typing import Dict, List, Sequence, Tuple
import weakref

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest
import pytz
from ulid import ULID

# CRITICAL: Set testing mode BEFORE any app imports!
os.environ.setdefault("is_testing", "true")
os.environ.setdefault("rate_limit_enabled", "false")
# Ensure tests never inherit a prod-like SITE_MODE at import time (DatabaseConfig + CORS/CSRF).
# We intentionally clear SITE_MODE later for legacy DB-safety behavior, but we must pin it
# here to prevent dotenv/user shell from affecting module import side effects.
os.environ["SITE_MODE"] = "int"
os.environ.setdefault("AVAILABILITY_PERF_DEBUG", "1")
os.environ.setdefault("AVAILABILITY_TEST_MEMORY_CACHE", "1")
os.environ.setdefault("SEED_AVAILABILITY", "0")
os.environ.setdefault("SEED_AVAILABILITY_WEEKS", "0")
os.environ.setdefault("SEED_DISABLE_SLOTS", "1")
os.environ.setdefault("INCLUDE_EMPTY_DAYS_IN_TESTS", "1")
os.environ.setdefault("INSTANT_DELIVER_IN_TESTS", "1")
os.environ.setdefault("PROMETHEUS_CACHE_IN_TESTS", "1")
os.environ.setdefault("DB_DIALECT", "postgresql")
if "sqlite" in os.getenv("TEST_DATABASE_URL", "").lower() or "sqlite" in os.getenv(
    "DATABASE_URL", ""
).lower():
    os.environ["DB_DIALECT"] = "sqlite"

# CRITICAL: Mock Resend API globally to prevent real emails in ANY test
import unittest.mock

# Create global mock that persists for all tests
global_resend_mock = unittest.mock.patch("resend.Emails.send")
mocked_send = global_resend_mock.start()
mocked_send.return_value = {"id": "test-email-id", "status": "sent"}

# Additional safety: Mock the entire resend module if needed

if "resend" not in sys.modules:
    resend_module_mock = unittest.mock.MagicMock()
    resend_module_mock.Emails.send.return_value = {"id": "test-email-id", "status": "sent"}
    sys.modules["resend"] = resend_module_mock

CONFIG_ENV_KEYS = [
    "SESSION_COOKIE_NAME",
    "SESSION_COOKIE_SAMESITE",
    "SESSION_COOKIE_SECURE",
    "EMAIL_PROVIDER",
    "RESEND_API_KEY",
    "TOTP_VALID_WINDOW",
    "SITE_MODE",
    "ENVIRONMENT",
]


@pytest.fixture
def anyio_backend():
    """Force anyio-based tests to run under asyncio backend."""
    return "asyncio"


@pytest.fixture(autouse=True)
def clear_base_service_metrics():
    """Clear BaseService metrics before each test to prevent state leakage."""
    from app.services.base import BaseService

    if hasattr(BaseService, "_class_metrics"):
        BaseService._class_metrics.clear()
    yield
    if hasattr(BaseService, "_class_metrics"):
        BaseService._class_metrics.clear()


@pytest.fixture
def event_loop():
    """Create an event loop for async tests and close Redis clients before teardown."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        try:
            from app.core.cache_redis import close_async_cache_redis_client

            loop.run_until_complete(close_async_cache_redis_client())
        except Exception:
            pass
        try:
            from app.ratelimit.redis_backend import close_async_rate_limit_redis_client

            loop.run_until_complete(close_async_rate_limit_redis_client())
        except Exception:
            pass
        try:
            from app.core.redis import close_async_redis_client

            loop.run_until_complete(close_async_redis_client())
        except Exception:
            pass
        loop.close()


@pytest.fixture(autouse=True)
def _cleanup_asyncio_run(monkeypatch):
    """Wrap asyncio.run to close async Redis clients created during ad-hoc loops."""
    original_run = asyncio.run

    def _run(coro):
        async def _wrapper():
            try:
                return await coro
            finally:
                try:
                    from app.core.cache_redis import close_async_cache_redis_client

                    await close_async_cache_redis_client()
                except Exception:
                    pass
                try:
                    from app.ratelimit.redis_backend import close_async_rate_limit_redis_client

                    await close_async_rate_limit_redis_client()
                except Exception:
                    pass
                try:
                    from app.core.redis import close_async_redis_client

                    await close_async_redis_client()
                except Exception:
                    pass

        return original_run(_wrapper())

    monkeypatch.setattr(asyncio, "run", _run)
    yield


_test_clients: "weakref.WeakSet[TestClient]" = weakref.WeakSet()


@pytest.fixture(scope="session", autouse=True)
def _track_test_clients():
    """Ensure TestClient instances are closed even when not used as a context manager."""
    original_init = TestClient.__init__

    def _init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _test_clients.add(self)

    TestClient.__init__ = _init
    try:
        yield
    finally:
        for client in list(_test_clients):
            try:
                client.close()
            except Exception:
                pass
        TestClient.__init__ = original_init

@pytest.fixture
def isolate_settings_env(monkeypatch):
    """Temporarily clear Settings-related env vars and reload the config module."""

    import app.core.config as cfg

    snapshot = os.environ.copy()
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    importlib.reload(cfg)

    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)
        importlib.reload(cfg)

# Add the backend directory to Python path so imports work
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# NOW we can set the settings
from app.core.config import settings

settings.is_testing = True
settings.rate_limit_enabled = False

from unittest.mock import MagicMock, Mock

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies.database import get_db as deps_get_db
from app.auth import get_password_hash

# Now we can import from app
from app.core.enums import PermissionName, RoleName
from app.database import Base, get_db
from app.main import fastapi_app as app  # Use FastAPI instance for tests
from app.models import SearchEvent, SearchHistory

# Ensure address and region models are registered so Base.metadata.create_all creates their tables
from app.models.address import InstructorServiceArea, NYCNeighborhood, UserAddress  # noqa: F401
from app.models.audit_log import AuditLog, AuditLogEntry
from app.models.availability_day import AvailabilityDay  # noqa: F401
from app.models.badge import (  # noqa: F401 ensures badge tables
    BadgeDefinition,
    BadgeProgress,
    StudentBadge,
)
from app.models.beta import BetaAccess, BetaInvite  # noqa: F401 ensure beta tables are registered
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation  # noqa: F401 ensure conversation table is created
from app.models.event_outbox import EventOutbox, NotificationDelivery  # noqa: F401
from app.models.instructor import InstructorProfile
from app.models.referrals import (  # noqa: F401 ensures tables are registered
    InstructorReferralPayout,
    ReferralAttribution,
    ReferralClick,
    ReferralCode,
    ReferralLimit,
    ReferralReward,
    WalletTransaction,
)
from app.models.region_boundary import RegionBoundary  # noqa: F401
from app.models.service_catalog import (
    InstructorService as Service,
    ServiceAnalytics,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory
from app.models.user import User
from app.models.webhook_event import WebhookEvent  # noqa: F401
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.config_service import ConfigService
from app.services.permission_service import PermissionService
from app.services.template_service import TemplateService
from app.utils.bitset import bits_from_windows

try:  # pragma: no cover - allow tests to run from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe

BOROUGH_ABBR: dict[str, str] = {
    "Manhattan": "MN",
    "Brooklyn": "BK",
    "Queens": "QN",
    "Bronx": "BR",
    "Staten Island": "SI",
}

BOROUGH_CENTROID: dict[str, tuple[float, float]] = {
    "Manhattan": (-73.985, 40.758),
    "Brooklyn": (-73.950, 40.650),
    "Queens": (-73.820, 40.730),
    "Bronx": (-73.900, 40.850),
    "Staten Island": (-74.150, 40.580),
}


def _square_polygon(lon: float, lat: float, delta: float = 0.01) -> dict:
    ring = [
        [lon - delta, lat - delta],
        [lon + delta, lat - delta],
        [lon + delta, lat + delta],
        [lon - delta, lat + delta],
        [lon - delta, lat - delta],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _ensure_boundary_geometry(boundary: RegionBoundary, borough: str) -> bool:
    metadata = dict(boundary.region_metadata or {})
    if metadata.get("geometry"):
        return False

    lon, lat = BOROUGH_CENTROID.get(borough, BOROUGH_CENTROID["Manhattan"])
    metadata["geometry"] = _square_polygon(lon, lat)
    boundary.region_metadata = metadata
    return True


def _ensure_boundary_columns(db: Session, boundary: RegionBoundary, borough: str) -> None:
    if not db.bind or db.bind.dialect.name == "sqlite":
        return
    try:
        has_boundary = db.execute(
            text("SELECT boundary IS NOT NULL FROM region_boundaries WHERE id = :id"),
            {"id": boundary.id},
        ).scalar()
    except Exception:
        return

    if has_boundary:
        return

    region_meta = boundary.region_metadata or {}
    geom = region_meta.get("geometry") if isinstance(region_meta, dict) else None
    if not geom:
        lon, lat = BOROUGH_CENTROID.get(borough, BOROUGH_CENTROID["Manhattan"])
        geom = _square_polygon(lon, lat)

    geom_expr = "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))"
    try:
        db.execute(
            text(
                f"""
                UPDATE region_boundaries
                SET boundary = {geom_expr},
                    centroid = ST_Centroid({geom_expr})
                WHERE id = :id
                """
            ),
            {"geom": json.dumps(geom), "id": boundary.id},
        )
        db.flush()
    except Exception:
        return

def unique_email(prefix: str = "test.user") -> str:
    """Generate a unique email for tests to avoid collisions."""
    # Use example.com instead of insta.test to avoid Pydantic EmailStr validation issues
    # example.com is a reserved domain specifically for documentation/examples and passes validation
    return f"{prefix}+{ULID()}@example.com"


__all__ = [
    "add_service_area",
    "add_service_areas_for_boroughs",
    "seed_service_areas_from_legacy",
    "_ensure_region_boundary",
    "unique_email",
]

def _ensure_region_boundary(db: Session, borough: str) -> RegionBoundary:
    """Find or create a RegionBoundary entry for the given borough."""

    normalized = (borough or "").strip()
    if not normalized:
        raise ValueError("borough must be a non-empty string")

    abbr = BOROUGH_ABBR.get(normalized, normalized[:2].upper()) or "XX"
    region_id = f"TEST-{abbr}"

    existing = db.get(RegionBoundary, region_id)
    if existing:
        if _ensure_boundary_geometry(existing, normalized):
            db.flush()
        _ensure_boundary_columns(db, existing, normalized)
        return existing

    lon, lat = BOROUGH_CENTROID.get(normalized, BOROUGH_CENTROID["Manhattan"])
    if db.bind and db.bind.dialect.name != "sqlite":
        try:
            candidate_id = db.execute(
                text(
                    """
                    SELECT id
                    FROM region_boundaries
                    WHERE parent_region = :parent_region
                      AND boundary IS NOT NULL
                      AND ST_Covers(
                          boundary::geometry,
                          ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geometry
                      )
                    LIMIT 1
                    """
                ),
                {"parent_region": normalized, "lng": lon, "lat": lat},
            ).scalar()
            if candidate_id:
                candidate = db.get(RegionBoundary, candidate_id)
                if candidate:
                    return candidate
        except Exception:
            pass

    boundary = RegionBoundary(
        id=region_id,
        region_type="nyc",
        region_code=f"{abbr}-TEST",
        region_name=f"{normalized} Test Neighborhood",
        parent_region=normalized,
        region_metadata={
            "nta_name": f"{normalized} Test Neighborhood",
            "nta_code": f"{abbr}-TEST",
            "borough": normalized,
            "geometry": _square_polygon(lon, lat),
        },
    )

    db.add(boundary)
    db.flush()
    _ensure_boundary_columns(db, boundary, normalized)
    return boundary


def add_service_area(db: Session, user: User, neighborhood_id: str) -> InstructorServiceArea:
    """Attach a service area row for the given user."""

    if db.get(User, user.id) is None:
        db.merge(user)
        db.flush()

    isa = (
        db.query(InstructorServiceArea)
        .filter(
            InstructorServiceArea.instructor_id == user.id,
            InstructorServiceArea.neighborhood_id == neighborhood_id,
        )
        .first()
    )
    if isa:
        if not isa.is_active:
            isa.is_active = True
            db.flush()
        return isa

    isa = InstructorServiceArea(
        instructor_id=user.id,
        neighborhood_id=neighborhood_id,
    )
    db.add(isa)
    db.flush()
    return isa


def add_service_areas_for_boroughs(db: Session, user: User, boroughs: Sequence[str]) -> None:
    """Attach service areas for each provided borough name."""

    for borough in boroughs:
        boundary = _ensure_region_boundary(db, borough)
        add_service_area(db, user=user, neighborhood_id=boundary.id)


def seed_service_areas_from_legacy(
    db: Session, user: User, legacy_value: str | None
) -> None:
    """Populate service areas based on a legacy comma-separated borough string."""

    parts = [part.strip() for part in (legacy_value or "").split(",") if part.strip()]
    add_service_areas_for_boroughs(db, user=user, boroughs=parts or ["Manhattan"])

# ============================================================================
# PRODUCTION DATABASE PROTECTION
# ============================================================================


def _validate_test_database_url(database_url: str) -> None:
    """
    Validate that we're not using a production database for tests.

    Raises:
        RuntimeError: If the database URL appears to be a production database
    """
    if not database_url:
        raise RuntimeError("No database URL configured for tests!")

    # Check against known production database providers
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
                "CRITICAL ERROR: ATTEMPTING TO RUN TESTS ON PRODUCTION DATABASE!\n"
                "=" * 60 + "\n"
                f"Database URL contains production indicator: '{indicator}'\n"
                f"URL: {database_url[:30]}...\n\n"
                f"Tests are configured to WIPE THE DATABASE after each test.\n"
                f"Running tests on production would DELETE ALL YOUR DATA!\n\n"
                f"To fix this:\n"
                f"1. Set TEST_DATABASE_URL to a local test database\n"
                f"2. Never use production database URLs for testing\n"
                f"3. Example: TEST_DATABASE_URL=postgresql://localhost/instainstru_test\n"
                f"=" * 60 + "\n"
            )

    # Warn if database doesn't have 'test' in the name
    test_indicators = ["test", "testing", "_test", "-test"]
    has_test_indicator = any(indicator in url_lower for indicator in test_indicators)

    if not has_test_indicator:
        print(
            f"\n⚠️  WARNING: Test database URL doesn't contain 'test' in its name.\n"
            f"   Consider using a clearly named test database to avoid confusion.\n"
            f"   Current: {database_url[:50]}...\n"
        )


# ============================================================================
# TEST DATABASE CONFIGURATION
# ============================================================================

# Force testing mode (lowercase to match settings)
os.environ["is_testing"] = "true"
settings.is_testing = True

# CRITICAL: Force INT database for all tests - ignore any environment flags
# This ensures tests ALWAYS use the INT database for safety
os.environ.pop("SITE_MODE", None)

# Get test database URL - this will now always use INT database
TEST_DATABASE_URL = settings.test_database_url

if not TEST_DATABASE_URL:
    # Try to use a default local test database if none configured
    TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/instainstru_int"
    print(
        f"\n⚠️  No test_database_url configured. Using default: {TEST_DATABASE_URL}\n"
        f"   Set test_database_url in your .env file for custom configuration.\n"
    )

# CRITICAL: Validate we're not using production
_validate_test_database_url(TEST_DATABASE_URL)

# Create test engine with the validated test database URL
test_engine = create_engine(
    TEST_DATABASE_URL,
    poolclass=None,  # Disable pooling for tests
)

# Verify we can connect and it's safe
try:
    with test_engine.connect() as conn:
        result = conn.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        print(f"\n✅ Connected to test database: {db_name}")

        # Extra safety: check table count
        result = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables " "WHERE table_schema = 'public'"))
        table_count = result.scalar()

        # Extract expected database name from TEST_DATABASE_URL
        from urllib.parse import urlparse

        parsed_url = urlparse(TEST_DATABASE_URL)
        expected_db_name = parsed_url.path.lstrip("/")

        # Verify we're using the expected test database
        if db_name != expected_db_name:
            raise RuntimeError(
                f"SAFETY CHECK FAILED: Expected test database '{expected_db_name}' "
                f"(from TEST_DATABASE_URL), but connected to '{db_name}'. "
                f"Aborting to prevent data loss."
            )

        # Log table count for information (no prompt needed in pytest)
        if table_count > 20:
            print(f"   Note: Test database has {table_count} tables (migrations already applied)")
except Exception as e:
    raise RuntimeError(f"Failed to connect to test database: {e}")

# Create test session factory with expire_on_commit=False to prevent stale ORM objects
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False)

_DB_PREPARED = False
_DB_PREPARE_LOCK = threading.Lock()
_CATALOG_SEEDED = False
_RBAC_SEEDED = False


def ensure_outbox_table() -> None:
    """Ensure event_outbox table exists (guard DDL to prevent conflicts)."""
    insp = inspect(test_engine)
    if insp.has_table("event_outbox"):
        return

    with test_engine.begin() as conn:
        try:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS event_outbox (
                        id VARCHAR(26) PRIMARY KEY,
                        event_type VARCHAR(100) NOT NULL,
                        aggregate_id VARCHAR(64) NOT NULL,
                        idempotency_key VARCHAR(255) UNIQUE NOT NULL,
                        payload JSONB NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        attempt_count INTEGER NOT NULL,
                        next_attempt_at TIMESTAMPTZ,
                        last_error TEXT,
                        created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
                    )
                    """
                )
            )
            if conn.dialect.name != "sqlite":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS notification_delivery (
                            id VARCHAR(26) PRIMARY KEY,
                            outbox_id VARCHAR(26) NOT NULL,
                            recipient_email VARCHAR(255) NOT NULL,
                            notification_type VARCHAR(50) NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                            FOREIGN KEY (outbox_id) REFERENCES event_outbox(id)
                        )
                        """
                    )
                )
        except IntegrityError as exc:
            # Concurrent creation can surface as duplicate pg_type rows; safe to ignore
            if "pg_type_typname_nsp_index" not in str(exc):
                raise


def _prepare_database() -> None:
    """Ensure extensions, tables, and constraints exist for tests."""
    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            insp = inspect(test_engine)
            reset_outbox = os.getenv("RESET_OUTBOX_SCHEMA", "0") == "1"
            if reset_outbox:
                if insp.has_table("notification_delivery"):
                    conn.execute(text("DROP TABLE IF EXISTS notification_delivery CASCADE"))
                if insp.has_table("event_outbox"):
                    conn.execute(text("DROP TABLE IF EXISTS event_outbox CASCADE"))
                # Postgres can rarely leave behind an orphaned composite type for a dropped/failed table
                # create, which then breaks subsequent CREATE TABLE with pg_type_typname_nsp_index errors.
                conn.execute(text("DROP TYPE IF EXISTS event_outbox CASCADE"))
            # These schemas evolve quickly during search/location work; drop so create_all
            # recreates them with the latest SQLAlchemy models for this test run.
            if insp.has_table("location_aliases"):
                conn.execute(text("DROP TABLE IF EXISTS location_aliases CASCADE"))
            if insp.has_table("unresolved_location_queries"):
                conn.execute(text("DROP TABLE IF EXISTS unresolved_location_queries CASCADE"))
            conn.commit()

    Base.metadata.create_all(bind=test_engine)

    # Ensure outbox table exists (guarded to prevent conflicts)
    ensure_outbox_table()

    # Keep users schema aligned with ORM models (tests reuse an existing DB).
    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS tokens_valid_after TIMESTAMPTZ
                    """
                )
            )
            conn.commit()

    # Keep instructor_profiles schema aligned with ORM models (tests reuse an existing DB).
    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(
                text(
                    """
                    ALTER TABLE instructor_profiles
                    ADD COLUMN IF NOT EXISTS commission_override_pct NUMERIC(5, 2)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE instructor_profiles
                    ADD COLUMN IF NOT EXISTS commission_override_until TIMESTAMPTZ
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE instructor_profiles
                    ADD COLUMN IF NOT EXISTS payout_hold BOOLEAN NOT NULL DEFAULT false
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE instructor_profiles
                    ADD COLUMN IF NOT EXISTS payout_hold_reason TEXT
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE instructor_profiles
                    ADD COLUMN IF NOT EXISTS payout_hold_at TIMESTAMPTZ
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE instructor_profiles
                    ADD COLUMN IF NOT EXISTS payout_hold_released_at TIMESTAMPTZ
                    """
                )
            )
            conn.commit()

    # Keep webhook_events schema aligned with ORM models (tests reuse an existing DB).
    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(
                text(
                    """
                    ALTER TABLE webhook_events
                    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE webhook_events
                    ADD COLUMN IF NOT EXISTS last_retry_at TIMESTAMPTZ
                    """
                )
            )
            conn.commit()

    # Keep region_boundaries schema aligned with ORM models (tests reuse an existing DB).
    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(text("ALTER TABLE region_boundaries ADD COLUMN IF NOT EXISTS name_embedding vector(1536)"))
            conn.commit()

    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1
                        FROM pg_indexes
                        WHERE tablename = 'region_boundaries'
                          AND indexname = 'region_boundaries_rtype_rcode_idx'
                      ) THEN
                        CREATE UNIQUE INDEX region_boundaries_rtype_rcode_idx
                          ON region_boundaries(region_type, region_code);
                      END IF;
                    END$$;
                    """
                )
            )
            conn.commit()

    with test_engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
            # availability_slots table removed - bitmap-only storage now
        conn.execute(
            text("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_location_type")
        )
        if conn.dialect.name != "sqlite":
            conn.execute(
                text("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_no_overlap_per_instructor")
            )
            conn.execute(
                text("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_no_overlap_per_student")
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD COLUMN IF NOT EXISTS booking_span tsrange
                    GENERATED ALWAYS AS (
                        tsrange(
                            (booking_date::timestamp + start_time),
                            CASE
                                WHEN end_time = time '00:00:00' AND start_time <> time '00:00:00'
                                    THEN (booking_date::timestamp + interval '1 day')
                                ELSE (booking_date::timestamp + end_time)
                            END,
                            '[)'
                        )
                    ) STORED
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT bookings_no_overlap_per_instructor
                    EXCLUDE USING gist (
                        instructor_id WITH =,
                        booking_span WITH &&
                    )
                    WHERE (cancelled_at IS NULL)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT bookings_no_overlap_per_student
                    EXCLUDE USING gist (
                        student_id WITH =,
                        booking_span WITH &&
                    )
                    WHERE (cancelled_at IS NULL)
                    """
                )
            )
            conn.execute(
                text("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS check_time_order")
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE bookings
                    ADD CONSTRAINT check_time_order
                    CHECK (
                        CASE
                            WHEN end_time = time '00:00:00' AND start_time <> time '00:00:00' THEN TRUE
                            ELSE start_time < end_time
                        END
                    )
                    """
                )
            )
        conn.execute(
            text(
                "ALTER TABLE bookings ADD CONSTRAINT ck_bookings_location_type "
                "CHECK (location_type IN ('student_location', 'instructor_location', 'online', 'neutral_location'))"
            )
        )
        conn.commit()

# ============================================================================
# Database Prep Guard
# ============================================================================

def ensure_test_database_ready() -> None:
    """Prepare test schema once per process, with a cross-process advisory lock."""
    global _DB_PREPARED
    if _DB_PREPARED:
        return

    with _DB_PREPARE_LOCK:
        if _DB_PREPARED:
            return

        if test_engine.dialect.name != "sqlite":
            with test_engine.connect() as conn:
                conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": 987654321})
                conn.commit()
                try:
                    _prepare_database()
                finally:
                    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": 987654321})
                    conn.commit()
        else:
            _prepare_database()

        _DB_PREPARED = True

# ============================================================================
# Helper Functions
# ============================================================================


def _ensure_rbac_roles():
    """Ensure RBAC roles and permissions exist in the test database."""
    global _RBAC_SEEDED
    if _RBAC_SEEDED:
        return

    from app.core.enums import PermissionName
    from app.models.rbac import Permission, Role, RolePermission

    session = TestSessionLocal()
    try:
        # Check if permissions are already set up
        existing_permissions = session.query(Permission).count()
        if existing_permissions > 0:
            # Already seeded, just return
            _RBAC_SEEDED = True
            return

        # Get or create standard roles
        roles = {}
        for role_name in [RoleName.ADMIN, RoleName.INSTRUCTOR, RoleName.STUDENT]:
            role = session.query(Role).filter_by(name=role_name).first()
            if not role:
                if role_name == RoleName.ADMIN:
                    role = Role(name=RoleName.ADMIN, description="Administrator with full access")
                elif role_name == RoleName.INSTRUCTOR:
                    role = Role(
                        name=RoleName.INSTRUCTOR, description="Instructor who can manage their profile and availability"
                    )
                else:  # STUDENT
                    role = Role(name=RoleName.STUDENT, description="Student who can book lessons")
                session.add(role)
                session.flush()
            roles[role_name] = role

        # Create all permissions
        permissions = {}
        for perm_name in PermissionName:
            perm = Permission(name=perm_name.value, description=f"Permission for {perm_name.value.replace('_', ' ')}")
            session.add(perm)
            permissions[perm_name.value] = perm

        session.flush()  # Get IDs

        # Assign permissions to roles
        # Admin gets everything
        admin_role = roles[RoleName.ADMIN]
        for perm in permissions.values():
            session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))

        # Student permissions
        student_role = roles[RoleName.STUDENT]
        student_perms = [
            PermissionName.MANAGE_OWN_PROFILE,
            PermissionName.VIEW_OWN_BOOKINGS,
            PermissionName.VIEW_OWN_SEARCH_HISTORY,
            PermissionName.CHANGE_OWN_PW,
            PermissionName.DELETE_OWN_ACCOUNT,
            PermissionName.VIEW_INSTRUCTORS,
            PermissionName.VIEW_INSTRUCTOR_AVAILABILITY,
            PermissionName.CREATE_BOOKINGS,
            PermissionName.CANCEL_OWN_BOOKINGS,
            PermissionName.VIEW_BOOKING_DETAILS,
            PermissionName.SEND_MESSAGES,
            PermissionName.VIEW_MESSAGES,
        ]
        for perm_name in student_perms:
            perm = permissions[perm_name.value]
            session.add(RolePermission(role_id=student_role.id, permission_id=perm.id))

        # Instructor permissions
        instructor_role = roles[RoleName.INSTRUCTOR]
        instructor_perms = [
            PermissionName.MANAGE_OWN_PROFILE,
            PermissionName.VIEW_OWN_BOOKINGS,
            PermissionName.VIEW_OWN_SEARCH_HISTORY,
            PermissionName.CHANGE_OWN_PW,
            PermissionName.DELETE_OWN_ACCOUNT,
            PermissionName.MANAGE_INSTRUCTOR_PROFILE,
            PermissionName.MANAGE_SERVICES,
            PermissionName.MANAGE_AVAILABILITY,
            PermissionName.VIEW_INCOMING_BOOKINGS,
            PermissionName.COMPLETE_BOOKINGS,
            PermissionName.CANCEL_STUDENT_BOOKINGS,
            PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
            PermissionName.SUSPEND_OWN_INSTRUCTOR_ACCOUNT,
            PermissionName.SEND_MESSAGES,
            PermissionName.VIEW_MESSAGES,
        ]
        for perm_name in instructor_perms:
            perm = permissions[perm_name.value]
            session.add(RolePermission(role_id=instructor_role.id, permission_id=perm.id))

        session.commit()
        print(f"✅ Created {len(roles)} RBAC roles with permissions")
        _RBAC_SEEDED = True
    except Exception as e:
        print(f"❌ Error creating RBAC roles: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_catalog_data():
    """Ensure catalog data is seeded for tests (3-level taxonomy)."""
    global _CATALOG_SEEDED
    if _CATALOG_SEEDED:
        return

    mod = _load_seed_taxonomy_module()
    seed_taxonomy = mod.seed_taxonomy

    # Create a separate session to check
    session = TestSessionLocal()
    try:
        # Check if the 3-level taxonomy is already present
        existing_categories = session.query(ServiceCategory).count()
        existing_services = session.query(ServiceCatalog).count()
        required_category_names = {
            "Music",
            "Sports & Fitness",
            "Tutoring & Test Prep",
            "Languages",
        }
        required_service_slugs = {"piano", "guitar", "yoga"}
        category_names = {row[0] for row in session.query(ServiceCategory.name).all()}
        service_slugs = {row[0] for row in session.query(ServiceCatalog.slug).all()}
        missing_required = (
            not required_category_names.issubset(category_names)
            or not required_service_slugs.issubset(service_slugs)
        )

        if existing_categories == 0 or existing_services == 0 or missing_required:
            print("\n🌱 Seeding taxonomy data for tests...")
            # Close session before seeding (seed_taxonomy creates its own)
            session.close()

            # Seed using the taxonomy seeder (DELETE-then-INSERT, idempotent)
            seed_taxonomy(db_url=TEST_DATABASE_URL, verbose=False)

            # Verify seeding worked
            session = TestSessionLocal()
            categories_count = session.query(ServiceCategory).count()
            services_count = session.query(ServiceCatalog).count()

            # Verify critical services exist
            piano = session.query(ServiceCatalog).filter_by(slug="piano").first()
            guitar = session.query(ServiceCatalog).filter_by(slug="guitar").first()
            yoga = session.query(ServiceCatalog).filter_by(slug="yoga").first()
            music = session.query(ServiceCategory).filter_by(name="Music").first()
            sports = session.query(ServiceCategory).filter_by(name="Sports & Fitness").first()

            if not piano or not guitar or not yoga or not music or not sports:
                raise RuntimeError(
                    "Critical catalog entries (Music, Sports & Fitness, piano, guitar, yoga) "
                    "not found after seeding"
                )

            print(f"✅ Seeded {categories_count} categories and {services_count} services")
        _CATALOG_SEEDED = True
    except Exception as e:
        print(f"\n❌ Error seeding catalog data: {e}")
        raise
    finally:
        session.close()


@lru_cache(maxsize=1)
def _load_seed_taxonomy_module():
    """Load taxonomy seeder module once for deterministic ID helpers."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seed_taxonomy",
        os.path.join(backend_dir, "scripts", "seed_data", "seed_taxonomy.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def _seeded_taxonomy_ids() -> tuple[set[str], set[str], set[str]]:
    """Return deterministic category/subcategory/service IDs from seed_taxonomy.py."""
    mod = _load_seed_taxonomy_module()

    category_ids: set[str] = set()
    subcategory_ids: set[str] = set()
    service_ids: set[str] = set()

    category_slug_by_name: dict[str, str] = {}
    for category in mod.CATEGORIES:
        category_name = str(category["name"])
        category_slug = str(category["slug"])
        category_slug_by_name[category_name] = category_slug
        category_ids.add(str(mod.deterministic_id("category", category_slug)))

    for category_name, subcategories in mod.TAXONOMY.items():
        cat_name = str(category_name)
        category_slug = category_slug_by_name.get(cat_name, mod.slugify(cat_name))
        for subcategory_name, _display_order, services in subcategories:
            sub_slug = mod.slugify(str(subcategory_name))
            sub_id = str(mod.deterministic_id("subcategory", f"{category_slug}:{sub_slug}"))
            subcategory_ids.add(sub_id)
            for service_name in services:
                svc_slug = mod.slugify(str(service_name))
                service_ids.add(
                    str(mod.deterministic_id("service", f"{category_slug}:{sub_slug}:{svc_slug}"))
                )

    return category_ids, subcategory_ids, service_ids


def create_test_session() -> Session:
    """Initialize and return a fresh SQLAlchemy session for tests."""
    if settings.is_production_database(TEST_DATABASE_URL):
        raise RuntimeError("CRITICAL: Refusing to create tables in what appears to be a production database!")

    ensure_test_database_ready()
    _ensure_catalog_data()
    _ensure_rbac_roles()
    return TestSessionLocal()


def cleanup_test_database() -> None:
    """Delete test data to preserve isolation between tests."""
    cleanup_db = TestSessionLocal()
    try:
        if os.getenv("PYTEST_VERBOSE"):
            print("\n🧹 Cleaning up test data...")

        cleanup_db.query(Booking).delete()
        cleanup_db.query(AvailabilityDay).delete()  # Bitmap-only storage now
        cleanup_db.query(Service).delete()  # This is InstructorService
        cleanup_db.query(StudentBadge).delete()
        cleanup_db.query(BadgeProgress).delete()
        cleanup_db.query(NotificationDelivery).delete()
        cleanup_db.query(EventOutbox).delete()
        cleanup_db.query(WebhookEvent).delete()
        cleanup_db.query(AuditLog).delete()
        cleanup_db.query(AuditLogEntry).delete()
        # Beta tables (BetaAccess has FK to BetaInvite.code, so delete Access first)
        cleanup_db.query(BetaAccess).delete()
        cleanup_db.query(BetaInvite).delete()

        seeded_category_ids, seeded_subcategory_ids, seeded_service_ids = _seeded_taxonomy_ids()
        # Keep deterministic baseline taxonomy; remove per-test taxonomy records.
        cleanup_db.query(ServiceCatalog).filter(
            ~ServiceCatalog.id.in_(seeded_service_ids)
        ).delete(synchronize_session=False)
        cleanup_db.query(ServiceSubcategory).filter(
            ~ServiceSubcategory.id.in_(seeded_subcategory_ids)
        ).delete(synchronize_session=False)
        cleanup_db.query(ServiceCategory).filter(
            ~ServiceCategory.id.in_(seeded_category_ids)
        ).delete(synchronize_session=False)

        existing_catalog_ids = select(ServiceCatalog.id)
        cleanup_db.query(ServiceAnalytics).filter(
            ~ServiceAnalytics.service_catalog_id.in_(existing_catalog_ids)
        ).delete(synchronize_session=False)

        cleanup_db.query(InstructorProfile).delete()
        cleanup_db.query(User).delete()
        cleanup_db.commit()
    except Exception as e:  # pragma: no cover - cleanup best effort
        print(f"\n⚠️  Error during test cleanup: {e}")
        cleanup_db.rollback()
    finally:
        cleanup_db.close()

# =========================================================================
# STRICT_SCHEMAS toggle fixture
# =========================================================================
import contextlib


@contextlib.contextmanager
def _strict_env():
    old = os.environ.get("STRICT_SCHEMAS")
    os.environ["STRICT_SCHEMAS"] = "true"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("STRICT_SCHEMAS", None)
        else:
            os.environ["STRICT_SCHEMAS"] = old


@pytest.fixture
def STRICT_ON():
    with _strict_env():
        yield


@pytest.fixture
def client(db: Session):
    """Create a test client with the test database."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps_get_db] = override_get_db

    # Use context manager so lifespan shutdown closes async clients (Redis, etc.).
    with TestClient(app) as test_client:
        yield test_client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _auth_test_mode(monkeypatch):
    """
    Force app into 'local/test' auth mode so cookie-only/session tests pass.
    Patch the actual settings object used by the app.
    """
    from app.core.config import settings

    # Patch the actual settings object used by the app
    for name, val in [
        ("app_env", "local"),
        ("allow_cookie_only_auth", True),
        ("disable_csrf_for_tests", True),
        ("test_mode_auth", True),
    ]:
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, val, raising=False)

    # Fallback environment flags for code paths that read os.environ
    monkeypatch.setenv("APP_ENV", "local", prepend=False)
    monkeypatch.setenv("ALLOW_COOKIE_ONLY_AUTH", "1", prepend=False)
    monkeypatch.setenv("DISABLE_CSRF_FOR_TESTS", "1", prepend=False)
    monkeypatch.setenv("TEST_MODE_AUTH", "1", prepend=False)


@pytest.fixture(scope="function")
def db():
    """
    Create a new database session for each test.
    This version works with TestClient.

    SAFETY: Only runs on validated test databases.
    """
    # Extra safety check before creating tables
    session = create_test_session()

    yield session

    # Cleanup
    session.rollback()
    session.close()

    cleanup_test_database()


@pytest.fixture
def unique_nyc_region_code(db: Session):
    """Yield a unique NYC region code and clean it up after the test."""
    code = f"Z{secrets.token_hex(2).upper()}"
    # First delete any service areas referencing the region (FK constraint is RESTRICT)
    db.execute(
        text(
            "DELETE FROM instructor_service_areas WHERE neighborhood_id IN "
            "(SELECT id FROM region_boundaries WHERE region_type = 'nyc' AND region_code = :code)"
        ),
        {"code": code},
    )
    db.execute(
        text("DELETE FROM region_boundaries WHERE region_type = 'nyc' AND region_code = :code"),
        {"code": code},
    )
    db.commit()
    try:
        yield code
    finally:
        # Clean up in correct order: service areas first, then region boundaries
        db.execute(
            text(
                "DELETE FROM instructor_service_areas WHERE neighborhood_id IN "
                "(SELECT id FROM region_boundaries WHERE region_type = 'nyc' AND region_code = :code)"
            ),
            {"code": code},
        )
        db.execute(
            text(
                "DELETE FROM region_boundaries WHERE region_type = 'nyc' AND region_code = :code"
            ),
            {"code": code},
        )
        db.commit()


@pytest.fixture
def enable_price_floors():
    """Enable production-like price floors for the duration of a test."""
    ensure_test_database_ready()
    session = TestSessionLocal()
    config_service = ConfigService(session)
    original_config, _ = config_service.get_pricing_config()
    original_config_copy = deepcopy(original_config)

    updated_config = deepcopy(original_config)
    updated_config.setdefault("price_floor_cents", {})
    updated_config["price_floor_cents"]["private_in_person"] = 8000
    updated_config["price_floor_cents"]["private_remote"] = 6000
    config_service.set_pricing_config(updated_config)
    session.commit()

    try:
        yield
    finally:
        config_service.set_pricing_config(original_config_copy)
        session.commit()
        session.close()


@pytest.fixture
def disable_price_floors():
    """Disable price floors for tests that assume low-price bookings."""
    ensure_test_database_ready()
    session = TestSessionLocal()
    config_service = ConfigService(session)
    original_config, _ = config_service.get_pricing_config()
    original_config_copy = deepcopy(original_config)

    updated_config = deepcopy(original_config)
    updated_config.setdefault("price_floor_cents", {})
    updated_config["price_floor_cents"]["private_in_person"] = 0
    updated_config["price_floor_cents"]["private_remote"] = 0
    config_service.set_pricing_config(updated_config)
    session.commit()

    try:
        yield
    finally:
        config_service.set_pricing_config(original_config_copy)
        session.commit()
        session.close()


# ============================================================================
# TEST FIXTURES (unchanged from original)
# ============================================================================


@pytest.fixture(scope="function")
def catalog_data(db: Session) -> dict:
    """Ensure service catalog data exists for tests."""
    # The YAML seeding has already loaded the catalog, just return it
    categories = db.query(ServiceCategory).all()
    services = db.query(ServiceCatalog).all()

    if not categories or not services:
        # If for some reason the catalog is empty, raise an error
        raise RuntimeError("Service catalog is empty - run scripts/seed_catalog_only.py first")

    return {"categories": categories, "services": services}


@pytest.fixture
def test_password():
    """Standard test password for all test users."""
    return "TestPassword123!"


@pytest.fixture
def test_student(db: Session, test_password: str) -> User:
    """Create a test student user."""
    # Use unique email to avoid collisions
    student_email = unique_email("test.student")
    # Check if user already exists and delete it (shouldn't happen with unique emails, but safety check)
    existing_user = db.query(User).filter(User.email == student_email).first()
    if existing_user:
        db.delete(existing_user)
        db.commit()

    student = User(
        email=student_email,
        hashed_password=get_password_hash(test_password),
        first_name="Test",
        last_name="Student",
        phone="+12125551234",
        zip_code="10001",
        is_active=True,
    )
    db.add(student)
    db.flush()

    # Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(student.id, RoleName.STUDENT)
    permission_service.grant_permission(student.id, PermissionName.CREATE_BOOKINGS.value)
    db.refresh(student)
    db.commit()
    return student


def _public_profile_kwargs(**profile_kwargs):
    """Build InstructorProfile kwargs with verified/live defaults."""

    defaults = {
        "bgc_status": "passed",
        "is_live": True,
        "bgc_completed_at": datetime.now(timezone.utc),
    }
    defaults.update(profile_kwargs)
    return defaults


@pytest.fixture(autouse=True)
def freeze_availability_now(monkeypatch):
    """Ensure availability computations see a consistent 'current' time in tests."""

    def _fake_get_user_now_by_id(user_id: str, db_session) -> datetime:
        user = db_session.query(User).filter(User.id == user_id).first()
        tz_name = getattr(user, "timezone", "America/New_York") if user else "America/New_York"
        tz = pytz.timezone(tz_name)
        today = datetime.now(tz).date()
        return tz.localize(datetime.combine(today, time(5, 0)))

    monkeypatch.setattr(
        "app.services.availability_service.get_user_now_by_id",
        _fake_get_user_now_by_id,
    )


@pytest.fixture
def test_instructor(db: Session, test_password: str) -> User:
    """Create a test instructor user with profile and services."""
    # Use unique email to avoid collisions
    instructor_email = unique_email("test.instructor")
    # Check if user already exists and delete it (shouldn't happen with unique emails, but safety check)
    existing_user = db.query(User).filter(User.email == instructor_email).first()
    if existing_user:
        # Delete profile first if it exists (cascade will handle services)
        if hasattr(existing_user, "instructor_profile") and existing_user.instructor_profile:
            db.delete(existing_user.instructor_profile)
        db.delete(existing_user)
        db.commit()

    # Create instructor user
    instructor = User(
        email=instructor_email,
        hashed_password=get_password_hash(test_password),
        first_name="Test",
        last_name="Instructor",
        phone="+12125551235",
        zip_code="10002",
        is_active=True,
    )
    db.add(instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    assigned = permission_service.assign_role(instructor.id, RoleName.INSTRUCTOR)
    if not assigned:
        db.commit()
    db.refresh(instructor)

    # Create instructor profile
    profile = InstructorProfile(
        user_id=instructor.id,
        **_public_profile_kwargs(
            bio="Test instructor bio",
            years_experience=5,
            min_advance_booking_hours=2,
            buffer_time_minutes=15,
        ),
    )
    db.add(profile)
    db.flush()

    # Ensure instructor has service area coverage for Manhattan and Brooklyn
    neighborhoods = [
        {
            "region_name": "Manhattan - Midtown",
            "region_code": "MN-MID",
            "parent_region": "Manhattan",
        },
        {
            "region_name": "Brooklyn - Williamsburg",
            "region_code": "BK-WIL",
            "parent_region": "Brooklyn",
        },
    ]

    for entry in neighborhoods:
        region_boundary = (
            db.query(RegionBoundary)
            .filter(
                RegionBoundary.region_type == "nyc",
                RegionBoundary.region_name == entry["region_name"],
            )
            .first()
        )
        if not region_boundary:
            region_boundary = RegionBoundary(
                region_type="nyc",
                region_code=entry["region_code"],
                region_name=entry["region_name"],
                parent_region=entry["parent_region"],
                region_metadata={
                    "borough": entry["parent_region"],
                    "nta_name": entry["region_name"],
                    "nta_code": entry["region_code"],
                },
            )
            db.add(region_boundary)
            db.flush()

        if _ensure_boundary_geometry(region_boundary, entry["parent_region"]):
            db.flush()
        _ensure_boundary_columns(db, region_boundary, entry["parent_region"])

        existing_link = (
            db.query(InstructorServiceArea)
            .filter(
                InstructorServiceArea.instructor_id == instructor.id,
                InstructorServiceArea.neighborhood_id == region_boundary.id,
            )
            .first()
        )
        if existing_link:
            existing_link.is_active = True
        else:
            db.add(
                InstructorServiceArea(
                    instructor_id=instructor.id,
                    neighborhood_id=region_boundary.id,
                    coverage_type="primary",
                    is_active=True,
                )
            )


    # Get catalog services - use actual services from seeded data (order by slug for deterministic order)
    catalog_services = (
        db.query(ServiceCatalog)
        .filter(ServiceCatalog.slug.in_(["piano", "guitar"]))
        .order_by(ServiceCatalog.slug)
        .all()
    )

    print(f"Found {len(catalog_services)} catalog services")
    for cs in catalog_services:
        print(f"  - {cs.name} ({cs.slug})")

    # If no catalog services found, the catalog_data fixture may have failed
    if not catalog_services:
        print("WARNING: No catalog services found. Checking if any exist...")
        all_catalog = db.query(ServiceCatalog).all()
        print(f"Total catalog services in DB: {len(all_catalog)}")
        for cs in all_catalog[:5]:  # Show first 5
            print(f"  - {cs.name} ({cs.slug})")
        raise RuntimeError("Required catalog services (piano, guitar) not found")

    # Create instructor services linked to catalog
    services = []
    for catalog_service in catalog_services:
        if catalog_service.slug == "piano":
            hourly_rate = 50.0
            duration_options = [30, 60, 90]
        else:  # guitar
            hourly_rate = 45.0
            duration_options = [60]

        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=hourly_rate,
            description=catalog_service.description,
            duration_options=duration_options,
            offers_travel=True,
            is_active=True,
        )
        services.append(service)
    for service in services:
        db.add(service)

    db.flush()
    db.commit()
    db.refresh(instructor)
    return instructor


@pytest.fixture
def test_instructor_2(db: Session, test_password: str) -> User:
    """Create a second test instructor user with profile."""
    # Use unique email to avoid collisions
    instructor_email = unique_email("test.instructor2")
    # Check if user already exists and delete it (shouldn't happen with unique emails, but safety check)
    existing_user = db.query(User).filter(User.email == instructor_email).first()
    if existing_user:
        # Delete profile first if it exists (cascade will handle services)
        if hasattr(existing_user, "instructor_profile") and existing_user.instructor_profile:
            db.delete(existing_user.instructor_profile)
        db.delete(existing_user)
        db.commit()

    # Create instructor user
    instructor = User(
        email=instructor_email,
        hashed_password=get_password_hash(test_password),
        first_name="Test",
        last_name="Instructor 2",
        phone="+12125551236",
        zip_code="10003",
        is_active=True,
    )
    db.add(instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(instructor.id, RoleName.INSTRUCTOR)
    db.refresh(instructor)

    # Create instructor profile
    profile = InstructorProfile(
        user_id=instructor.id,
        **_public_profile_kwargs(
            bio="Second test instructor bio",
            years_experience=3,
            min_advance_booking_hours=1,
            buffer_time_minutes=10,
        ),
    )
    db.add(profile)
    db.flush()

    neighborhoods = [
        {
            "region_name": "Queens - Astoria",
            "region_code": "QN-AST",
            "parent_region": "Queens",
        },
        {
            "region_name": "Bronx - Fordham",
            "region_code": "BX-FOR",
            "parent_region": "Bronx",
        },
    ]

    for entry in neighborhoods:
        region_boundary = (
            db.query(RegionBoundary)
            .filter(
                RegionBoundary.region_type == "nyc",
                RegionBoundary.region_name == entry["region_name"],
            )
            .first()
        )
        if not region_boundary:
            region_boundary = RegionBoundary(
                region_type="nyc",
                region_code=entry["region_code"],
                region_name=entry["region_name"],
                parent_region=entry["parent_region"],
                region_metadata={
                    "borough": entry["parent_region"],
                    "nta_name": entry["region_name"],
                    "nta_code": entry["region_code"],
                },
            )
            db.add(region_boundary)
            db.flush()

        if _ensure_boundary_geometry(region_boundary, entry["parent_region"]):
            db.flush()
        _ensure_boundary_columns(db, region_boundary, entry["parent_region"])

        existing_link = (
            db.query(InstructorServiceArea)
            .filter(
                InstructorServiceArea.instructor_id == instructor.id,
                InstructorServiceArea.neighborhood_id == region_boundary.id,
            )
            .first()
        )
        if existing_link:
            existing_link.is_active = True
        else:
            db.add(
                InstructorServiceArea(
                    instructor_id=instructor.id,
                    neighborhood_id=region_boundary.id,
                    coverage_type="primary",
                    is_active=True,
                )
            )

    db.commit()
    db.refresh(instructor)
    return instructor


@pytest.fixture
def bitmap_repo(db: Session) -> AvailabilityDayRepository:
    """Provide AvailabilityDayRepository instance for tests."""
    return AvailabilityDayRepository(db)


@pytest.fixture
def seed_bitmap_week(
    db: Session,
    bitmap_repo: AvailabilityDayRepository,
) -> callable:
    """
    Fixture that returns a helper function to seed a week of availability.

    Usage:
        seed_week_fn = seed_bitmap_week
        seed_week_fn(instructor_id, monday, {
            "2025-01-06": [("09:00", "10:00"), ("14:00", "15:00")],
            "2025-01-07": [("10:00", "11:00")],
        })
    """

    def _seed_week(
        instructor_id: str,
        monday: date,
        windows_by_day: Dict[str, List[Tuple[str, str]]],
    ) -> None:
        """Seed availability for a week."""
        from pathlib import Path
        import sys

        # Add tests directory to path if needed
        tests_dir = Path(__file__).parent
        if str(tests_dir) not in sys.path:
            sys.path.insert(0, str(tests_dir))

        from _utils.bitmap_avail import seed_week

        seed_week(db, instructor_id, monday, windows_by_day)

    return _seed_week


@pytest.fixture
def test_instructor_with_availability(db: Session, test_instructor: User) -> User:
    """
    Create a test instructor with availability for the next 7 days.

    UPDATED: Creates availability using bitmap storage (AvailabilityDayRepository).
    """
    # Add availability for the next 7 days using bitmap storage
    today = datetime.now(timezone.utc).date()
    repo = AvailabilityDayRepository(db)

    items = []
    for i in range(7):
        target_date = today + timedelta(days=i)
        # Create windows: 9-12 and 14-17
        windows = [
            ("09:00:00", "12:00:00"),
            ("14:00:00", "17:00:00"),
        ]
        bits = bits_from_windows(windows)
        items.append((target_date, bits))

    if items:
        repo.upsert_week(test_instructor.id, items)
        db.flush()
        db.commit()

    return test_instructor


@pytest.fixture
def test_booking(db: Session, test_student: User, test_instructor_with_availability: User) -> Booking:
    """
    Create a test booking for tomorrow.

    UPDATED: Creates bookings without any reference to availability_slot_id,
    following the clean architecture from Session v56.
    """
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)

    # Get instructor's profile and service
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    # Ensure profile exists (some tests may not create it earlier)
    if profile is None:
        profile = InstructorProfile(
            user_id=test_instructor_with_availability.id,
            **_public_profile_kwargs(
                bio="Test instructor bio",
                years_experience=5,
                min_advance_booking_hours=2,
                buffer_time_minutes=15,
            ),
        )
        db.add(profile)
        db.flush()

    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active == True)
        .first()
    )
    if service is None:
        # Create a basic active service if none exists
        catalog_service = (
            db.query(ServiceCatalog)
            .filter(ServiceCatalog.slug.in_(["piano", "guitar"]))
            .order_by(ServiceCatalog.slug)
            .first()
        )
        if not catalog_service:
            raise RuntimeError("Required catalog services (piano, guitar) not found")
        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=50.0,
            description=catalog_service.description,
            duration_options=[60],
            is_active=True,
        )
        db.add(service)
        db.flush()

    # Get service name from catalog
    catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.id == service.service_catalog_id).first()
    service_name = catalog_service.name if catalog_service else "Test Service"

    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=tomorrow,
        start_time=time(9, 0),
        end_time=time(12, 0),
        service_name=service_name,
        hourly_rate=service.hourly_rate,
        total_price=float(service.hourly_rate) * 3,
        duration_minutes=180,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test Location",
        service_area="Manhattan",
        offset_index=0,
        cancel_duplicate=True,
    )
    return booking


@pytest.fixture
def auth_headers_student(test_student: User) -> dict:
    """Get auth headers for test student."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_student.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_instructor(test_instructor: User) -> dict:
    """Get auth headers for test instructor."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_instructor.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_instructor_2(test_instructor_2: User) -> dict:
    """Get auth headers for second test instructor."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_instructor_2.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(test_student: User) -> dict:
    """Get auth headers for test student (default auth headers)."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_student.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db: Session, test_password: str) -> User:
    existing = db.query(User).filter(User.email == "test.admin@example.com").first()
    if existing:
        return existing

    user = User(
        email="test.admin@example.com",
        hashed_password=get_password_hash(test_password),
        first_name="Test",
        last_name="Admin",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()

    permission_service = PermissionService(db)
    permission_service.assign_role(user.id, RoleName.ADMIN)
    db.refresh(user)
    db.commit()
    return user


@pytest.fixture
def mcp_service_user(db: Session, test_password: str) -> User:
    existing = db.query(User).filter(User.email == "admin@instainstru.com").first()
    if existing:
        return existing

    user = User(
        email="admin@instainstru.com",
        hashed_password=get_password_hash(test_password),
        first_name="MCP",
        last_name="Service",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()

    permission_service = PermissionService(db)
    permission_service.assign_role(user.id, RoleName.ADMIN)
    db.refresh(user)
    db.commit()
    return user


@pytest.fixture
def mcp_service_headers(mcp_service_user: User) -> dict:
    settings.mcp_service_token = SecretStr("test-mcp-token")
    return {"Authorization": "Bearer test-mcp-token"}


@pytest.fixture
def auth_headers_admin(admin_user: User) -> dict:
    from app.auth import create_access_token

    token = create_access_token(data={"sub": admin_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_instructor_with_bookings(db: Session, test_instructor_with_availability: User, test_student: User) -> User:
    """
    Create a test instructor with services that have bookings.

    UPDATED: Creates bookings without any reference to availability slots.
    """
    # Get instructor's profile
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    if not profile:
        raise ValueError(f"No profile found for instructor {test_instructor_with_availability.id}")

    # Get the first service (order by ID for deterministic selection)
    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active == True)
        .order_by(Service.id)
        .first()
    )

    if not service:
        raise ValueError(f"No active service found for profile {profile.id}")

    # Get service name from catalog
    catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.id == service.service_catalog_id).first()
    service_name = catalog_service.name if catalog_service else "Test Service"

    tomorrow = date.today() + timedelta(days=1)

    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=tomorrow,
        start_time=time(9, 0),
        end_time=time(12, 0),
        service_name=service_name,
        hourly_rate=service.hourly_rate,
        total_price=float(service.hourly_rate) * 3,
        duration_minutes=180,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test Location",
        offset_index=0,
        cancel_duplicate=True,
    )

    return test_instructor_with_availability


@pytest.fixture
def test_instructor_with_inactive_service(db: Session, test_instructor: User) -> User:
    """Create a test instructor with an inactive service."""
    # Get instructor's profile
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

    if not profile:
        raise ValueError(f"No profile found for instructor {test_instructor.id}")

    # Get a catalog service to link to - use any existing one
    catalog_service = db.query(ServiceCatalog).first()
    if not catalog_service:
        raise RuntimeError("No catalog services found - database not seeded properly")

    # Create an inactive service linked to catalog
    inactive_service = Service(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=60.0,
        description="This service is inactive",
        duration_options=[60],
        is_active=False,
    )
    db.add(inactive_service)
    db.flush()

    return test_instructor


# ============================================================================
# NOTIFICATION SERVICE FIXTURES
# ============================================================================


@pytest.fixture
def mock_cache():
    """Mock cache service for testing."""
    mock = Mock()
    mock.get = Mock(return_value=None)
    mock.set = Mock(return_value=True)
    mock.delete = Mock(return_value=True)
    mock.delete_pattern = Mock(return_value=0)
    return mock


@pytest.fixture
def email_service(db: Session, mock_cache):
    """Create EmailService with dependencies."""
    from app.services.email import EmailService

    service = EmailService(db, mock_cache)
    # Mock the actual sending to prevent real emails in tests
    service.send_email = Mock(return_value={"id": "test-email-id", "status": "sent"})
    return service


@pytest.fixture
def template_service(db: Session):
    """Create a TemplateService instance for testing."""
    return TemplateService(db, None)


@pytest.fixture
def notification_service(db: Session, template_service, email_service):
    """Create a NotificationService instance for testing."""
    from app.services.notification_service import NotificationService

    return NotificationService(db, None, template_service, email_service)


@pytest.fixture
def mock_email_service():
    """Mock email service to avoid sending real emails in tests."""
    mock = Mock()
    mock.send_email = Mock(return_value={"id": "test-email-id", "status": "sent"})
    return mock


@pytest.fixture
def mock_notification_service(db: Session, template_service, email_service):
    """
    Create a NotificationService with mocked email sending.
    This replaces the old mock_notification_service fixture.
    """
    from app.services.notification_service import NotificationService

    service = NotificationService(db, None, template_service, email_service)

    # The email service is already mocked in the email_service fixture
    # Also create sync mocks for the main methods
    service.send_booking_confirmation = MagicMock(return_value=True)
    service.send_cancellation_notification = MagicMock(return_value=True)
    service.send_reminder_emails = MagicMock(return_value=0)

    return service


@pytest.fixture
def notification_service_with_mocked_email(db: Session, template_service, email_service):
    """Create a NotificationService with real template rendering but mocked email sending."""
    from app.services.notification_service import NotificationService

    # email_service fixture already has mocked send_email
    return NotificationService(db, None, template_service, email_service)


@pytest.fixture
def sample_categories(db: Session) -> list[ServiceCategory]:
    """Create sample service categories for testing (3-level taxonomy)."""
    categories = [
        ServiceCategory(
            name="Music",
            subtitle="Instrument Voice Theory",
            description="Musical instruction",
            display_order=1,
        ),
        ServiceCategory(
            name="Sports & Fitness",
            subtitle="",
            description="Physical fitness and sports",
            display_order=2,
        ),
        ServiceCategory(
            name="Languages",
            subtitle="Learn new languages",
            description="Language instruction",
            display_order=3,
        ),
    ]

    persisted: list[ServiceCategory] = []
    for category in categories:
        existing = (
            db.query(ServiceCategory).filter(ServiceCategory.name == category.name).first()
        )
        if existing:
            persisted.append(existing)
        else:
            db.add(category)
            persisted.append(category)

    db.commit()
    return persisted


@pytest.fixture
def sample_subcategories(
    db: Session, sample_categories: list[ServiceCategory]
) -> list[ServiceSubcategory]:
    """Create sample subcategories for the 3-level taxonomy."""
    subcategories = [
        # Music subcategories
        ServiceSubcategory(
            category_id=sample_categories[0].id,
            name="Piano",
            display_order=1,
        ),
        ServiceSubcategory(
            category_id=sample_categories[0].id,
            name="Guitar",
            display_order=2,
        ),
        ServiceSubcategory(
            category_id=sample_categories[0].id,
            name="Violin",
            display_order=3,
        ),
        # Sports subcategories
        ServiceSubcategory(
            category_id=sample_categories[1].id,
            name="Yoga & Pilates",
            display_order=1,
        ),
        ServiceSubcategory(
            category_id=sample_categories[1].id,
            name="Personal Training",
            display_order=2,
        ),
        # Language subcategories
        ServiceSubcategory(
            category_id=sample_categories[2].id,
            name="Spanish",
            display_order=1,
        ),
    ]

    persisted: list[ServiceSubcategory] = []
    for sub in subcategories:
        existing = (
            db.query(ServiceSubcategory)
            .filter(
                ServiceSubcategory.category_id == sub.category_id,
                ServiceSubcategory.name == sub.name,
            )
            .first()
        )
        if existing:
            persisted.append(existing)
        else:
            db.add(sub)
            persisted.append(sub)

    db.commit()
    return persisted


@pytest.fixture
def sample_catalog_services(
    db: Session, sample_subcategories: list[ServiceSubcategory]
) -> list[ServiceCatalog]:
    """Create sample catalog services for testing (3-level taxonomy)."""
    services = [
        # Music services (under Piano, Guitar, Violin subcategories)
        ServiceCatalog(
            subcategory_id=sample_subcategories[0].id,  # Piano
            name="Piano Lessons",
            slug="piano-lessons",
            description="Learn piano",
            search_terms=["piano", "keyboard"],
            display_order=1,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
        ServiceCatalog(
            subcategory_id=sample_subcategories[1].id,  # Guitar
            name="Guitar Lessons",
            slug="guitar-lessons",
            description="Learn guitar",
            search_terms=["guitar", "acoustic", "electric"],
            display_order=2,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
        ServiceCatalog(
            subcategory_id=sample_subcategories[2].id,  # Violin
            name="Violin Lessons",
            slug="violin-lessons",
            description="Learn violin",
            search_terms=["violin", "strings"],
            display_order=3,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
        # Sports & Fitness services
        ServiceCatalog(
            subcategory_id=sample_subcategories[3].id,  # Yoga & Pilates
            name="Yoga",
            slug="yoga",
            description="Yoga instruction",
            search_terms=["yoga", "meditation"],
            display_order=1,
            online_capable=True,
            requires_certification=True,
            is_active=True,
        ),
        ServiceCatalog(
            subcategory_id=sample_subcategories[4].id,  # Personal Training
            name="Personal Training",
            slug="personal-training",
            description="One-on-one fitness training",
            search_terms=["fitness", "training", "gym"],
            display_order=2,
            online_capable=False,
            requires_certification=True,
            is_active=True,
        ),
        # Language services
        ServiceCatalog(
            subcategory_id=sample_subcategories[5].id,  # Spanish
            name="Spanish",
            slug="spanish",
            description="Learn Spanish",
            search_terms=["spanish", "espanol"],
            display_order=1,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
    ]

    persisted_services: list[ServiceCatalog] = []
    for service in services:
        existing = db.query(ServiceCatalog).filter(ServiceCatalog.slug == service.slug).first()
        if existing:
            persisted_services.append(existing)
        else:
            db.add(service)
            persisted_services.append(service)

    db.commit()
    return persisted_services


@pytest.fixture
def sample_instructors_with_services(db: Session, test_password: str) -> list[User]:
    """Create sample instructors with services linked to catalog."""
    instructors = []

    # Import unique data generator
    from tests.fixtures.unique_test_data import unique_data

    # Piano instructor - use unique email to avoid conflicts
    piano_email = unique_data.unique_email("piano.instructor")

    piano_instructor = User(
        email=piano_email,
        hashed_password=get_password_hash(test_password),
        is_active=True,
        first_name="Piano",
        last_name=unique_data.unique_name("Teacher"),
        phone="+12125550000",
        zip_code="10001",
    )
    db.add(piano_instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(piano_instructor.id, RoleName.INSTRUCTOR)
    db.refresh(piano_instructor)
    db.commit()

    piano_profile = InstructorProfile(
        user_id=piano_instructor.id,
        **_public_profile_kwargs(
            bio="Expert piano teacher",
            years_experience=10,
            min_advance_booking_hours=24,
        ),
    )
    db.add(piano_profile)
    db.commit()

    # Find piano service from catalog
    piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "piano").first()
    if not piano_catalog:
        raise RuntimeError("Piano service not found in catalog")

    piano_service = Service(
        instructor_profile_id=piano_profile.id,
        service_catalog_id=piano_catalog.id,
        description="Expert piano instruction",
        hourly_rate=75.0,
        duration_options=[30, 60, 90],
        is_active=True,
    )
    db.add(piano_service)
    db.commit()  # Commit to ensure service is created

    # Update analytics for Piano
    piano_analytics = db.query(ServiceAnalytics).filter(ServiceAnalytics.service_catalog_id == piano_catalog.id).first()
    if not piano_analytics:
        piano_analytics = ServiceAnalytics(service_catalog_id=piano_catalog.id)
        db.add(piano_analytics)
    piano_analytics.active_instructors = 1
    piano_analytics.search_count_30d = 100  # This will result in demand_score ~= 85
    piano_analytics.booking_count_30d = 17  # These values affect the computed demand_score
    piano_analytics.search_count_7d = 30  # For trending calculation

    instructors.append(piano_instructor)

    # Yoga instructor - use unique email to avoid conflicts
    yoga_email = unique_data.unique_email("yoga.instructor")

    yoga_instructor = User(
        email=yoga_email,
        hashed_password=get_password_hash(test_password),
        is_active=True,
        first_name="Yoga",
        last_name=unique_data.unique_name("Teacher"),
        phone="+12125550000",
        zip_code="10001",
    )
    db.add(yoga_instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(yoga_instructor.id, RoleName.INSTRUCTOR)
    db.refresh(yoga_instructor)
    db.commit()

    yoga_profile = InstructorProfile(
        user_id=yoga_instructor.id,
        **_public_profile_kwargs(
            bio="Certified yoga instructor",
            years_experience=5,
            min_advance_booking_hours=24,
        ),
    )
    db.add(yoga_profile)
    db.commit()

    # Find yoga service from catalog
    yoga_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "yoga").first()
    if not yoga_catalog:
        raise RuntimeError("Yoga service not found in catalog")

    yoga_service = Service(
        instructor_profile_id=yoga_profile.id,
        service_catalog_id=yoga_catalog.id,
        description="Professional yoga instruction",
        hourly_rate=60.0,
        duration_options=[60, 90],
        is_active=True,
    )
    db.add(yoga_service)
    db.commit()  # Commit to ensure service is created

    # Update analytics for Yoga
    yoga_analytics = db.query(ServiceAnalytics).filter(ServiceAnalytics.service_catalog_id == yoga_catalog.id).first()
    if not yoga_analytics:
        yoga_analytics = ServiceAnalytics(service_catalog_id=yoga_catalog.id)
        db.add(yoga_analytics)
    yoga_analytics.active_instructors = 1
    yoga_analytics.search_count_30d = 120  # This will result in higher demand_score
    yoga_analytics.booking_count_30d = 18  # These values affect the computed demand_score
    yoga_analytics.search_count_7d = 40  # For trending calculation

    instructors.append(yoga_instructor)

    db.commit()
    return instructors


@pytest.fixture
def mock_cache_service():
    """Create a mock cache service for testing."""
    mock = Mock()
    mock.get = Mock(return_value=None)
    mock.set = Mock(return_value=True)
    mock.delete = Mock(return_value=True)
    return mock


# Privacy Service Test Fixtures
@pytest.fixture
def sample_user_for_privacy(db):
    """Create a sample user with related data for privacy testing."""
    from datetime import datetime, timezone

    user = User(
        email="privacy_test@example.com",
        first_name="Privacy",
        last_name="Test User",
        phone="+12125550000",
        zip_code="10001",
        hashed_password="hashed_password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add search history
    search = SearchHistory(
        user_id=user.id,
        search_query="math tutoring",
        normalized_query="math tutoring",  # Required field
        results_count=5,
        search_count=3,
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add(search)

    # Add search events
    event = SearchEvent(
        user_id=user.id,
        search_query="math",
        results_count=10,
        search_context={},
    )
    db.add(event)

    # Note: AlertHistory doesn't have user_id - it's for system alerts

    db.commit()
    return user


@pytest.fixture
def sample_instructor_for_privacy(db):
    """Create a sample instructor user with profile for privacy testing."""
    user = User(
        email="privacy_instructor@example.com",
        first_name="Privacy",
        last_name="Test Instructor",
        phone="+12125550000",
        zip_code="10001",
        hashed_password="hashed_password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add instructor profile
    instructor = InstructorProfile(
        user_id=user.id,
        **_public_profile_kwargs(
            bio="Experienced math tutor",
            years_experience=5,
        ),
    )
    db.add(instructor)
    db.commit()

    return user


@pytest.fixture
def sample_admin_for_privacy(db):
    """Create a sample admin user for privacy testing."""
    user = User(
        email="privacy_admin@example.com",
        first_name="Privacy",
        last_name="Admin User",
        phone="+12125550000",
        zip_code="10001",
        hashed_password="hashed_password",
    )
    db.add(user)
    db.commit()
    return user


from backend.tests._inventory import dump_inventory, record_runtime_skip
import pytest


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture runtime skip reasons."""
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.skipped:
        # Extract skip reason
        reason = ""
        if hasattr(rep, "longreprtext") and rep.longreprtext:
            reason = rep.longreprtext.splitlines()[-1][:200]
        elif hasattr(rep, "longrepr") and rep.longrepr:
            reason = str(rep.longrepr)[:200]
        record_runtime_skip(item.nodeid, reason)


def pytest_sessionfinish(session, exitstatus):
    """Cleanup after all tests are done."""
    # Dump inventory before cleanup
    dump_inventory()
    # Stop the global Resend mock
    global_resend_mock.stop()
