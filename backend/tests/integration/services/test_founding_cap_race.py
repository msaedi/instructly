"""
Concurrency tests for founding instructor cap enforcement.
"""

from concurrent.futures import ThreadPoolExecutor
import threading

from sqlalchemy.orm import Session, sessionmaker
import ulid

from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository


def _seed_instructor_profiles(db: Session, count: int) -> list[str]:
    profile_ids: list[str] = []
    for _ in range(count):
        user = User(
            id=str(ulid.ULID()),
            email=f"founding.race.{ulid.ULID()}@example.com",
            hashed_password="hashed",
            first_name="Test",
            last_name="User",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=user.id,
        )
        db.add(profile)
        db.flush()
        profile_ids.append(profile.id)

    db.commit()
    return profile_ids


def test_try_claim_founding_status_concurrent_cap_enforced(db: Session) -> None:
    profile_ids = _seed_instructor_profiles(db, 5)
    SessionMaker = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    barrier = threading.Barrier(len(profile_ids))

    def _worker(profile_id: str) -> bool:
        session = SessionMaker()
        try:
            repo = InstructorProfileRepository(session)
            barrier.wait(timeout=5)
            granted, _ = repo.try_claim_founding_status(profile_id, cap=1)
            session.commit()
            return granted
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=len(profile_ids)) as executor:
        results = list(executor.map(_worker, profile_ids))

    assert results.count(True) == 1

    db.expire_all()
    total = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.is_founding_instructor.is_(True))
        .count()
    )
    assert total == 1


def test_cap_zero_grants_nobody(db: Session) -> None:
    """When cap=0, no one should get founding status."""
    profile_ids = _seed_instructor_profiles(db, 1)
    repo = InstructorProfileRepository(db)

    granted, count = repo.try_claim_founding_status(profile_ids[0], cap=0)

    assert granted is False
    assert count == 0


def test_already_founding_is_idempotent(db: Session) -> None:
    """Re-granting to already-founding instructor returns success without double-counting."""
    profile_ids = _seed_instructor_profiles(db, 1)
    repo = InstructorProfileRepository(db)

    # First grant
    granted1, count1 = repo.try_claim_founding_status(profile_ids[0], cap=10)
    db.commit()
    assert granted1 is True
    assert count1 == 1

    # Second grant (same profile) - should be idempotent
    granted2, count2 = repo.try_claim_founding_status(profile_ids[0], cap=10)
    assert granted2 is True  # Should still return True (already founding)
    assert count2 == 1  # Count shouldn't increase


def test_at_cap_rejects_new_but_allows_existing(db: Session) -> None:
    """When exactly at cap, existing founders OK but new claims rejected."""
    profile_ids = _seed_instructor_profiles(db, 2)
    repo = InstructorProfileRepository(db)

    # Create founding instructor (cap=1)
    granted1, _ = repo.try_claim_founding_status(profile_ids[0], cap=1)
    db.commit()
    db.expire_all()  # Clear session cache to ensure fresh reads
    assert granted1 is True

    # Try to add another - should fail
    granted2, count2 = repo.try_claim_founding_status(profile_ids[1], cap=1)
    assert granted2 is False
    assert count2 == 1

    # Commit and expire to ensure clean transaction for next call
    db.commit()
    db.expire_all()

    # Re-grant to existing founder - should succeed (idempotent)
    granted3, count3 = repo.try_claim_founding_status(profile_ids[0], cap=1)
    assert granted3 is True
    assert count3 == 1


def test_nonexistent_profile_returns_false(db: Session) -> None:
    """Claiming founding status for non-existent profile returns False."""
    repo = InstructorProfileRepository(db)

    granted, count = repo.try_claim_founding_status("nonexistent_profile_id", cap=10)

    assert granted is False
    assert count == 0  # No founding instructors yet


def test_negative_cap_grants_nobody(db: Session) -> None:
    """Negative cap should reject all claims."""
    profile_ids = _seed_instructor_profiles(db, 1)
    repo = InstructorProfileRepository(db)

    granted, count = repo.try_claim_founding_status(profile_ids[0], cap=-1)

    assert granted is False
    assert count == 0
