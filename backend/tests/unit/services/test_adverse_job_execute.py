from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from tests.unit.services._adverse_helpers import ensure_adverse_schema
import ulid

from app.core.config import settings
from app.models.instructor import BGCAdverseActionEvent, InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import BackgroundCheckWorkflowService


def _create_profile(db: Session) -> tuple[InstructorProfile, InstructorProfileRepository, BackgroundCheckWorkflowService]:
    ensure_adverse_schema(db)

    user = User(
        email="execute-adverse@example.com",
        hashed_password="hashed",
        first_name="Final",
        last_name="Action",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = "review"
    profile.is_live = False
    db.add(profile)
    db.flush()

    repo = InstructorProfileRepository(db)
    workflow = BackgroundCheckWorkflowService(repo)
    return profile, repo, workflow


def _prepare_notice(repo: InstructorProfileRepository, profile: InstructorProfile, sent_at: datetime) -> str:
    notice_id = str(ulid.ULID())
    repo.set_pre_adverse_notice(profile.id, notice_id, sent_at)
    return notice_id


def test_execute_finalizes_once(db: Session) -> None:
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.bgc_suppress_adverse_emails = True
    try:
        profile, repo, workflow = _create_profile(db)
        sent_at = datetime(2024, 3, 6, 12, 0, tzinfo=timezone.utc)
        notice_id = _prepare_notice(repo, profile, sent_at)
        db.commit()

        scheduled_at = sent_at + timedelta(days=7)
        succeeded = workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)
        assert succeeded

        db.expire_all()
        refreshed = db.query(InstructorProfile).filter_by(id=profile.id).one()
        assert refreshed.bgc_status == "failed"
        assert refreshed.is_live is False
        assert refreshed.bgc_final_adverse_sent_at is not None

        event = (
            db.query(BGCAdverseActionEvent)
            .filter_by(profile_id=profile.id, notice_id=notice_id)
            .one()
        )
        assert event.event_type == "final_adverse_sent"
    finally:
        settings.bgc_suppress_adverse_emails = original_suppress


def test_execute_is_idempotent(db: Session) -> None:
    profile, repo, workflow = _create_profile(db)
    sent_at = datetime(2024, 5, 1, 9, 0, tzinfo=timezone.utc)
    notice_id = _prepare_notice(repo, profile, sent_at)
    db.commit()

    scheduled_at = sent_at + timedelta(days=7)
    assert workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)
    assert not workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)

    events = (
        db.query(BGCAdverseActionEvent)
        .filter_by(profile_id=profile.id, notice_id=notice_id)
        .all()
    )
    assert len(events) == 1


def test_execute_skips_when_dispute_open(db: Session) -> None:
    profile, repo, workflow = _create_profile(db)
    sent_at = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
    notice_id = _prepare_notice(repo, profile, sent_at)

    profile.bgc_in_dispute = True
    profile.bgc_dispute_opened_at = sent_at + timedelta(days=1)
    db.commit()

    scheduled_at = sent_at + timedelta(days=7)
    assert not workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)

    db.expire_all()
    refreshed = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert refreshed.bgc_status == "review"
    assert refreshed.is_live is False


def test_execute_skips_if_superseded(db: Session) -> None:
    profile, repo, workflow = _create_profile(db)
    sent_at = datetime(2024, 7, 1, 11, 0, tzinfo=timezone.utc)
    first_notice = _prepare_notice(repo, profile, sent_at)
    db.commit()

    newer_notice = str(ulid.ULID())
    repo.set_pre_adverse_notice(profile.id, newer_notice, sent_at + timedelta(days=1))
    db.commit()

    scheduled_at = sent_at + timedelta(days=7)
    assert not workflow.execute_final_adverse_action(profile.id, first_notice, scheduled_at)


def test_execute_skips_if_status_changed(db: Session) -> None:
    profile, repo, workflow = _create_profile(db)
    sent_at = datetime(2024, 8, 1, 11, 0, tzinfo=timezone.utc)
    notice_id = _prepare_notice(repo, profile, sent_at)

    profile.bgc_status = "passed"
    profile.is_live = True
    db.commit()

    scheduled_at = sent_at + timedelta(days=7)
    assert not workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)
