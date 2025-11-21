from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.core.config import settings
from app.models.instructor import BackgroundCheck, BackgroundJob, InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import BackgroundCheckWorkflowService
from app.services.email import EmailService
from tests.unit.services._adverse_helpers import ensure_adverse_schema


def _reset_jobs(db: Session) -> None:
    db.query(BackgroundJob).delete()
    db.commit()


def _create_profile(db: Session, email: str = "integration-adverse@example.com") -> InstructorProfile:
    user = User(
        email=email,
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


def test_consider_result_sends_review_email_once(db: Session) -> None:
    """
    Test that when a report comes back with result='consider' (needs review),
    the workflow sends the neutral review status email exactly once and sets
    bgc_review_email_sent_at.
    """
    ensure_adverse_schema(db)
    _reset_jobs(db)
    original_testing = settings.is_testing
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.is_testing = False
    settings.bgc_suppress_adverse_emails = False
    try:
        profile = _create_profile(db, email="review-once@example.com")
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        completed_at = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
        report_id = str(ulid.ULID())
        profile.bgc_report_id = report_id
        db.commit()

        # Patch EmailService.send_email to track calls
        with patch.object(EmailService, "send_email", autospec=True) as mocked_send:
            workflow.handle_report_completed(
                report_id=report_id,
                result="consider",
                package="essential",
                env=settings.checkr_env,
                completed_at=completed_at,
            )

            db.flush()
            db.refresh(profile)

            # Verify status is set to review
            assert profile.bgc_status == "review"
            assert profile.is_live is False

            # Verify review email was sent exactly once
            assert mocked_send.call_count == 1

            # Verify bgc_review_email_sent_at is set
            assert profile.bgc_review_email_sent_at is not None

            # Verify no BackgroundJob for final adverse action was created
            final_adverse_jobs = (
                db.query(BackgroundJob)
                .filter(BackgroundJob.type == "background_check.final_adverse_action")
                .all()
            )
            assert len(final_adverse_jobs) == 0, "No final adverse action jobs should be created in new workflow"

    finally:
        settings.is_testing = original_testing
        settings.bgc_suppress_adverse_emails = original_suppress


def test_review_email_is_idempotent(db: Session) -> None:
    """
    Test that calling handle_report_completed multiple times for the same
    'consider' result does not send duplicate review emails (idempotent behavior).
    """
    ensure_adverse_schema(db)
    _reset_jobs(db)
    original_testing = settings.is_testing
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.is_testing = False
    settings.bgc_suppress_adverse_emails = False
    try:
        profile = _create_profile(db, email="review-idempotent@example.com")
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        completed_at = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
        report_id = str(ulid.ULID())
        profile.bgc_report_id = report_id
        db.commit()

        with patch.object(EmailService, "send_email", autospec=True) as mocked_send:
            # First webhook - should send email
            workflow.handle_report_completed(
                report_id=report_id,
                result="consider",
                package="essential",
                env=settings.checkr_env,
                completed_at=completed_at,
            )

            db.flush()
            db.refresh(profile)
            assert mocked_send.call_count == 1
            first_sent_at = profile.bgc_review_email_sent_at
            assert first_sent_at is not None

            # Second webhook (replay or update) - should NOT send another email
            workflow.handle_report_completed(
                report_id=report_id,
                result="consider",
                package="essential",
                env=settings.checkr_env,
                completed_at=completed_at,
            )

            db.flush()
            db.refresh(profile)

            # Email should still only have been sent once
            assert mocked_send.call_count == 1

            # Timestamp should remain unchanged
            assert profile.bgc_review_email_sent_at == first_sent_at

    finally:
        settings.is_testing = original_testing
        settings.bgc_suppress_adverse_emails = original_suppress


def test_consider_result_sets_review_status(db: Session) -> None:
    """
    Test that a 'consider' result properly sets bgc_status to 'review'
    and the profile appears as expected for the BGC review queue.
    """
    ensure_adverse_schema(db)
    _reset_jobs(db)

    profile = _create_profile(db, email="review-status@example.com")
    repo = InstructorProfileRepository(db)
    workflow = BackgroundCheckWorkflowService(repo)

    completed_at = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
    report_id = str(ulid.ULID())
    profile.bgc_report_id = report_id
    profile.bgc_status = "pending"  # Start in pending state
    db.commit()

    # Suppress emails for this test - we're just checking status updates
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.bgc_suppress_adverse_emails = True
    try:
        workflow.handle_report_completed(
            report_id=report_id,
            result="consider",
            package="essential",
            env=settings.checkr_env,
            completed_at=completed_at,
        )

        db.flush()
        db.refresh(profile)

        # Verify profile is in review state
        assert profile.bgc_status == "review"
        assert profile.is_live is False
        assert profile.bgc_completed_at is not None

        # Verify background check history was recorded
        history_entry = (
            db.query(BackgroundCheck)
            .filter(BackgroundCheck.instructor_id == profile.id)
            .order_by(BackgroundCheck.created_at.desc())
            .first()
        )
        assert history_entry is not None
        assert history_entry.result == "consider"
        assert history_entry.package == "essential"

    finally:
        settings.bgc_suppress_adverse_emails = original_suppress


def test_clear_result_does_not_send_review_email(db: Session) -> None:
    """
    Test that a 'clear' result does not trigger the review email
    (review emails are only for 'consider' results).
    """
    ensure_adverse_schema(db)
    _reset_jobs(db)
    original_testing = settings.is_testing
    original_suppress = settings.bgc_suppress_adverse_emails
    settings.is_testing = False
    settings.bgc_suppress_adverse_emails = False
    try:
        profile = _create_profile(db, email="clear-result@example.com")
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        completed_at = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
        report_id = str(ulid.ULID())
        profile.bgc_report_id = report_id
        profile.bgc_status = "pending"
        db.commit()

        with patch.object(EmailService, "send_email", autospec=True) as mocked_send:
            workflow.handle_report_completed(
                report_id=report_id,
                result="clear",
                package="standard",
                env=settings.checkr_env,
                completed_at=completed_at,
            )

            db.flush()
            db.refresh(profile)

            # Verify status is set to passed (not review)
            assert profile.bgc_status == "passed"

            # Verify NO review email was sent
            assert mocked_send.call_count == 0

            # Verify bgc_review_email_sent_at is NOT set
            assert profile.bgc_review_email_sent_at is None

    finally:
        settings.is_testing = original_testing
        settings.bgc_suppress_adverse_emails = original_suppress
