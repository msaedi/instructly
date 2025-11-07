"""Selective gating: skip slot-era tests at collection time."""
# Fallback in case this file is run in isolation or a different rootdir is inferred
try:
    import backend  # noqa: F401
except ModuleNotFoundError:
    from pathlib import Path
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[3]  # <repo>/
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from datetime import date
from pathlib import Path

from backend.tests._inventory import record_collection_skip
from backend.tests._slot_era_detector import is_slot_era_file
import pytest
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.models.instructor import InstructorProfile
from app.models.user import User


def pytest_ignore_collect(collection_path: Path, config):
    """Ignore slot-era test files at collection time."""
    p = str(collection_path)
    if "backend/tests/integration/services" not in p and not p.endswith("/backend/tests/integration/services"):
        return False

    if not p.endswith(".py"):
        return False

    # Return True (ignore) if slot-era, False (collect) otherwise
    if is_slot_era_file(p):
        record_collection_skip(p, "slot-era (AST) in integration/services")
        return True  # Ignore slot-era files
    return False  # Collect safe files


@pytest.fixture
def unique_instructor(db: Session) -> tuple[str, str]:
    """Return (instructor_id, user_id) ULIDs for a fresh instructor with profile."""
    u = User(
        email=f"uniq.instructor.{date.today().isoformat()}@example.com",
        hashed_password=get_password_hash("test123!"),
        first_name="Test",
        last_name="Instructor",
        zip_code="10001",
        is_active=True,
        account_status="active",
        timezone="America/New_York",
    )
    db.add(u)
    db.flush()
    prof = InstructorProfile(user_id=u.id)
    db.add(prof)
    db.commit()
    return (u.id, u.id)


@pytest.fixture
def instructor_id(unique_instructor: tuple[str, str]) -> str:
    """Extract instructor_id from unique_instructor tuple."""
    return unique_instructor[0]


@pytest.fixture
def user_id(unique_instructor: tuple[str, str]) -> str:
    """Extract user_id from unique_instructor tuple."""
    return unique_instructor[1]


@pytest.fixture
def clear_week_bits(db: Session):
    """Fixture that returns a function to clear week bits for an instructor."""
    from backend.tests._utils.bitmap_seed import clear_week_bits as clear_fn

    def _clear(instructor_id: str, week_start: date, weeks: int = 1):
        clear_fn(db, instructor_id, week_start, weeks)

    return _clear


@pytest.fixture(autouse=True)
def _seed_week_for_weekop(request):
    """Seed availability for week-operation tests that use unique_instructor."""
    # Only seed for week-op modules to reduce side-effects
    nodeid = getattr(request.node, "nodeid", "")
    if "test_week_operation_" not in nodeid:
        return

    # Check if this test uses unique_instructor
    try:
        db = request.getfixturevalue("db")
        unique_instructor = request.getfixturevalue("unique_instructor")
        instructor_id = unique_instructor[0]
        user_id = unique_instructor[1]

        # Ensure instructor has a service (needed for some tests)
        from sqlalchemy import select

        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService, ServiceCatalog

        instructor = db.get(User, user_id)
        if instructor:
            profile = db.execute(
                select(InstructorProfile).where(InstructorProfile.user_id == instructor.id)
            ).scalar_one_or_none()

            if profile:
                # Check if instructor has a service
                service = db.execute(
                    select(InstructorService).where(
                        InstructorService.instructor_profile_id == profile.id
                    )
                ).scalar_one_or_none()

                if not service:
                    # Create a default service
                    catalog = db.execute(
                        select(ServiceCatalog).where(ServiceCatalog.name == "Guitar")
                    ).scalar_one_or_none()

                    if not catalog:
                        catalog = ServiceCatalog(
                            name="Guitar",
                            slug="guitar",
                            description="Test Guitar service",
                            is_active=True,
                        )
                        db.add(catalog)
                        db.flush()

                    service = InstructorService(
                        instructor_profile_id=profile.id,
                        service_catalog_id=catalog.id,
                        hourly_rate=120.00,
                        duration_options=[60],
                        is_active=True,
                    )
                    db.add(service)
                    db.commit()

        # Seed a generous 2-week window so copy/apply tests have data
        from backend.tests._utils.bitmap_seed import seed_full_week
        seed_full_week(db, instructor_id, start="09:00:00", end="18:00:00", weeks=2)
    except (pytest.FixtureLookupError, KeyError):
        # Test doesn't use unique_instructor - skip seeding
        pass
    except Exception:
        # Other errors - don't crash tests
        pass
