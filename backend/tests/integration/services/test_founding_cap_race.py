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
