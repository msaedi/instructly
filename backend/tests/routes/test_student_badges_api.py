from datetime import datetime, timedelta, timezone
import importlib
from typing import Dict, Tuple

import pytest

from app.auth import create_access_token, get_password_hash
from app.core.enums import RoleName
from app.models.badge import BadgeProgress, StudentBadge
from app.models.user import User
from app.services.permission_service import PermissionService

EXPECTED_BADGE_SLUGS = [
    "welcome_aboard",
    "foundation_builder",
    "first_steps",
    "dedicated_learner",
    "momentum_starter",
    "consistent_learner",
    "top_student",
    "explorer",
    "favorite_partnership",
    "year_one_learner",
]

EXPECTED_DESCRIPTIONS = {
    "welcome_aboard": "Complete your first lesson on iNSTAiNSTRU.",
    "foundation_builder": "Reach 3 completed lessons to build early momentum.",
    "first_steps": "You earned this by completing 5 lessons.",
    "dedicated_learner": "Complete 10 lessons to unlock this milestone.",
    "momentum_starter": (
        "Book your next lesson within 7 days and complete it within 21 days with the same instructor."
    ),
    "consistent_learner": (
        "Complete at least one lesson each week for 3 consecutive weeks (with a 1-day grace window)."
    ),
    "top_student": (
        "Earn outstanding feedback: high average rating with multiple reviews and reliable attendance."
    ),
    "explorer": (
        "Take lessons across 3 different categories and rebook at least once in any category."
    ),
    "favorite_partnership": "Complete 10 lessons with the same instructor.",
    "year_one_learner": (
        "Be an active student for 12 months with 20+ total lessons and a recent lesson in the last 60 days."
    ),
}


@pytest.fixture
def core_badges_seeded(db):
    """Invoke the production badge seeder so tests use the canonical data."""
    seed_module = importlib.import_module("scripts.seed_data")
    engine = db.get_bind()
    seed_module.seed_badge_definitions(engine, verbose=False)
    return True


def _refresh_definition_map(db) -> Dict[str, object]:
    from app.models.badge import BadgeDefinition

    rows = (
        db.query(BadgeDefinition)
        .filter(BadgeDefinition.slug.in_(EXPECTED_BADGE_SLUGS))
        .all()
    )
    return {row.slug: row for row in rows}


def _seed_student_with_awards(db, definitions) -> Tuple[User, dict]:
    """Create Emma Johnson, assign role, and seed award/progress rows."""
    target_email = "emma.johnson@example.com"
    existing = db.query(User).filter(User.email == target_email).first()
    if existing:
        db.query(StudentBadge).filter(StudentBadge.student_id == existing.id).delete()
        db.query(BadgeProgress).filter(BadgeProgress.student_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    permission_service = PermissionService(db)
    emma = User(
        email=target_email,
        hashed_password=get_password_hash("TestPassword123!"),
        first_name="Emma",
        last_name="Johnson",
        zip_code="10001",
        is_active=True,
    )
    db.add(emma)
    db.flush()
    permission_service.assign_role(emma.id, RoleName.STUDENT)

    now = datetime.now(timezone.utc)
    for slug in ["first_steps", "dedicated_learner"]:
        badge_def = definitions[slug]
        db.add(
            StudentBadge(
                student_id=emma.id,
                badge_id=badge_def.id,
                status="confirmed",
                awarded_at=now,
                confirmed_at=now,
                progress_snapshot={"current": 1, "goal": 1},
            )
        )

    db.flush()

    db.add(
        BadgeProgress(
            student_id=emma.id,
            badge_id=definitions["momentum_starter"].id,
            current_progress={"current": 1, "goal": 3},
        )
    )
    db.add(
        BadgeProgress(
            student_id=emma.id,
            badge_id=definitions["top_student"].id,
            current_progress={"current": 8, "goal": 10},
        )
    )
    db.commit()

    token = create_access_token(data={"sub": emma.email})
    return emma, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def emma_with_badges(db, core_badges_seeded):
    definitions = _refresh_definition_map(db)
    student, headers = _seed_student_with_awards(db, definitions)
    return student, headers


def test_student_badges_listing(client, emma_with_badges):
    student, headers = emma_with_badges

    response = client.get("/api/students/badges", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == len(EXPECTED_BADGE_SLUGS)
    slugs = [item["slug"] for item in payload]
    assert slugs == EXPECTED_BADGE_SLUGS

    for item in payload:
        assert item["description"] == EXPECTED_DESCRIPTIONS[item["slug"]]

    first_steps = next(item for item in payload if item["slug"] == "first_steps")
    assert first_steps["earned"] is True
    assert first_steps["progress"]["percent"] == 100.0

    top_student = next(item for item in payload if item["slug"] == "top_student")
    assert top_student["earned"] is False
    assert top_student["progress"] is None

    momentum = next(item for item in payload if item["slug"] == "momentum_starter")
    assert momentum["earned"] is False
    assert momentum["progress"] is not None
    assert momentum["progress"]["percent"] == round((1 / 3) * 100, 2)


def test_student_badges_filters(client, emma_with_badges):
    student, headers = emma_with_badges

    earned_response = client.get("/api/students/badges/earned", headers=headers)
    assert earned_response.status_code == 200
    earned = earned_response.json()
    assert {badge["slug"] for badge in earned} == {"first_steps", "dedicated_learner"}

    progress_response = client.get("/api/students/badges/progress", headers=headers)
    assert progress_response.status_code == 200
    progress_items = progress_response.json()
    assert {badge["slug"] for badge in progress_items} == {"momentum_starter"}
    assert progress_items[0]["progress"] is not None


def test_revoked_award_not_earned(client, db, emma_with_badges):
    (student, headers) = emma_with_badges
    definitions = _refresh_definition_map(db)
    revoked_definition = definitions["welcome_aboard"]

    now = datetime.now(timezone.utc)
    db.add(
        StudentBadge(
            student_id=student.id,
            badge_id=revoked_definition.id,
            status="revoked",
            awarded_at=now - timedelta(days=14),
            revoked_at=now - timedelta(days=7),
            progress_snapshot={"current": 1, "goal": 1},
        )
    )
    db.add(
        BadgeProgress(
            student_id=student.id,
            badge_id=revoked_definition.id,
            current_progress={"current": 1, "goal": 1, "percent": 100},
        )
    )
    db.commit()

    response = client.get("/api/students/badges", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    revoked_entry = next(item for item in payload if item["slug"] == "welcome_aboard")
    assert revoked_entry["earned"] is False
    assert revoked_entry["status"] == "revoked"
    assert revoked_entry["progress"]["current"] == 1
    assert revoked_entry["progress"]["goal"] == 1

    earned_response = client.get("/api/students/badges/earned", headers=headers)
    assert earned_response.status_code == 200
    earned_slugs = {badge["slug"] for badge in earned_response.json()}
    assert "welcome_aboard" not in earned_slugs
