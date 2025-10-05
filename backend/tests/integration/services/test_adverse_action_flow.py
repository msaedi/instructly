from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from sqlalchemy.orm import Session
from tests.conftest import mocked_send
from tests.unit.services._adverse_helpers import ensure_adverse_schema
import ulid

from app.core.config import settings
from app.database import SessionLocal
from app.models.instructor import BackgroundCheck, BackgroundJob, InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import (
    BackgroundCheckWorkflowService,
    FinalAdversePayload,
)


def _reset_jobs(db: Session) -> None:
    db.query(BackgroundJob).delete()
    db.commit()


def _create_profile(db: Session) -> InstructorProfile:
    user = User(
        email="integration-adverse@example.com",
        hashed_password="hashed",
        first_name="Integration",
        last_name="Adverse",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = "review"
    profile.is_live = False
    db.add(profile)
    db.flush()
    return profile


def test_report_completed_encrypts_report_id(db: Session) -> None:
    ensure_adverse_schema(db)
    if not settings.bgc_encryption_key:
        pytest.skip("BGC_ENCRYPTION_KEY not configured")

    _reset_jobs(db)
    profile = _create_profile(db)
    repo = InstructorProfileRepository(db)
    workflow = BackgroundCheckWorkflowService(repo)

    report_id = str(ulid.ULID())
    profile.bgc_report_id = report_id
    completed_at = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    db.commit()

    workflow.handle_report_completed(
        report_id=report_id,
        result="clear",
        package="standard",
        env=settings.checkr_env,
        completed_at=completed_at,
    )

    db.flush()
    db.refresh(profile)
    raw_value = getattr(profile, "_bgc_report_id", None)

    assert profile.bgc_report_id == report_id
    assert raw_value and raw_value.startswith("v1:") and len(raw_value) > 64

    history_entry = (
        db.query(BackgroundCheck)
        .filter(BackgroundCheck.instructor_id == profile.id)
        .order_by(BackgroundCheck.created_at.desc())
        .first()
    )
    assert history_entry is not None
    assert history_entry.report_id_enc and len(history_entry.report_id_enc) > 0


def test_pre_to_final_adverse_flow(db: Session) -> None:
    ensure_adverse_schema(db)
    _reset_jobs(db)
    original_testing = settings.is_testing
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.is_testing = False
    settings.bgc_suppress_adverse_emails = False
    mocked_send.reset_mock()
    try:
        profile = _create_profile(db)
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        completed_at = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
        report_id = str(ulid.ULID())
        profile.bgc_report_id = report_id
        db.commit()
        workflow.handle_report_completed(
            report_id=report_id,
            result="consider",
            package="essential",
            env=settings.checkr_env,
            completed_at=completed_at,
        )

        db.flush()
        job = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.type == "background_check.final_adverse_action")
            .one()
        )

        payload_raw = job.payload
        if not isinstance(payload_raw, dict):
            raise AssertionError("Final adverse job payload is not a mapping")
        payload = cast(FinalAdversePayload, payload_raw)
        notice_id = payload["pre_adverse_notice_id"]
        scheduled_at = job.available_at or datetime.now(timezone.utc)

        db.commit()
        workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)

        db.expire_all()
        refreshed = db.query(InstructorProfile).filter_by(id=profile.id).one()
        assert refreshed.bgc_status == "failed"
        assert refreshed.is_live is False
        assert refreshed.bgc_final_adverse_sent_at is not None

        # Pre + Final emails
        assert mocked_send.call_count == 2
    finally:
        settings.is_testing = original_testing
        settings.bgc_suppress_adverse_emails = original_suppress


def test_final_adverse_skips_when_dispute_open(db: Session) -> None:
    ensure_adverse_schema(db)
    _reset_jobs(db)
    original_testing = settings.is_testing
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.is_testing = False
    settings.bgc_suppress_adverse_emails = False
    mocked_send.reset_mock()
    try:
        profile = _create_profile(db)
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        completed_at = datetime(2024, 4, 1, 12, 0, tzinfo=timezone.utc)
        report_id = str(ulid.ULID())
        profile.bgc_report_id = report_id
        db.commit()
        workflow.handle_report_completed(
            report_id=report_id,
            result="consider",
            package="essential",
            env=settings.checkr_env,
            completed_at=completed_at,
        )

        db.flush()
        job = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.type == "background_check.final_adverse_action")
            .one()
        )

        payload_raw = job.payload
        if not isinstance(payload_raw, dict):
            raise AssertionError("Final adverse job payload is not a mapping")
        payload = cast(FinalAdversePayload, payload_raw)
        notice_id = payload["pre_adverse_notice_id"]
        scheduled_at = job.available_at or datetime.now(timezone.utc)

        historic_sent = datetime.now(timezone.utc) - timedelta(days=7)
        dispute_opened = historic_sent + timedelta(days=1)
        db.query(InstructorProfile).filter_by(id=profile.id).update(
            {
                InstructorProfile.bgc_pre_adverse_sent_at: historic_sent,
                InstructorProfile.bgc_in_dispute: True,
                InstructorProfile.bgc_dispute_opened_at: dispute_opened,
            }
        )
        payload["pre_adverse_sent_at"] = historic_sent.isoformat()
        db.commit()

        with SessionLocal() as check_session:
            stored = check_session.query(InstructorProfile).filter_by(id=profile.id).one()
            assert stored.bgc_in_dispute is True
            assert stored.bgc_dispute_opened_at is not None
            assert stored.bgc_dispute_opened_at >= stored.bgc_pre_adverse_sent_at

        result = workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)
        assert not result

        db.expire_all()
        refreshed = db.query(InstructorProfile).filter_by(id=profile.id).one()
        assert refreshed.bgc_status == "review"
        assert refreshed.is_live is False

        # Only the pre-adverse email should have been sent
        assert mocked_send.call_count == 1
    finally:
        settings.is_testing = original_testing
        settings.bgc_suppress_adverse_emails = original_suppress
