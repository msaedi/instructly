from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session
from tests.unit.services._adverse_helpers import ensure_adverse_schema
import ulid

from app.core.config import settings
from app.models.instructor import BackgroundJob, InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import (
    FINAL_ADVERSE_BUSINESS_DAYS,
    FINAL_ADVERSE_JOB_TYPE,
    BackgroundCheckWorkflowService,
)
from app.utils.business_days import add_us_business_days, us_federal_holidays


def _holidays_for(dt: datetime) -> set[date]:
    return (
        us_federal_holidays(dt.year - 1)
        | us_federal_holidays(dt.year)
        | us_federal_holidays(dt.year + 1)
    )


def _clear_jobs(db: Session) -> None:
    db.query(BackgroundJob).delete()
    db.flush()


def _create_profile(
    db: Session,
    *,
    in_dispute: bool,
    pre_adverse_sent_at: datetime | None,
    notice_id: str | None,
    final_sent_at: datetime | None = None,
    status: str = "review",
) -> InstructorProfile:
    ensure_adverse_schema(db)

    user = User(
        email=f"bgc-dispute-{str(ulid.ULID()).lower()[:10]}@example.com",
        hashed_password="hashed",
        first_name="Dispute",
        last_name="Tester",
        zip_code="10001",
        timezone="America/New_York",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = status
    profile.bgc_in_dispute = in_dispute
    profile.bgc_pre_adverse_sent_at = pre_adverse_sent_at
    profile.bgc_pre_adverse_notice_id = notice_id
    profile.bgc_final_adverse_sent_at = final_sent_at
    db.add(profile)
    db.flush()
    return profile


@pytest.mark.anyio
async def test_resume_final_adverse_enqueues_immediately(db: Session) -> None:
    original_testing = settings.is_testing
    settings.is_testing = False
    try:
        _clear_jobs(db)
        now = datetime.now(timezone.utc)
        holidays = _holidays_for(now)
        target_days = FINAL_ADVERSE_BUSINESS_DAYS + 1
        pre_sent = now
        while target_days > 0:
            pre_sent -= timedelta(days=1)
            if pre_sent.weekday() < 5 and pre_sent.date() not in holidays:
                target_days -= 1
        profile = _create_profile(
            db,
            in_dispute=True,
            pre_adverse_sent_at=pre_sent,
            notice_id="notice-123",
        )

        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        resumed, scheduled_for = await workflow.resolve_dispute_and_resume_final_adverse(profile.id)
        db.flush()

        assert resumed is True
        assert scheduled_for is None

        jobs = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.type == FINAL_ADVERSE_JOB_TYPE)
            .all()
        )
        assert len(jobs) == 1
        job = jobs[0]
        assert job.available_at is not None
        assert job.available_at <= datetime.now(timezone.utc) + timedelta(seconds=1)

        db.refresh(profile)
        assert profile.bgc_in_dispute is False
        assert profile.bgc_dispute_resolved_at is not None
    finally:
        settings.is_testing = original_testing


@pytest.mark.anyio
async def test_resume_final_adverse_schedules_remaining_window(db: Session) -> None:
    original_testing = settings.is_testing
    settings.is_testing = False
    try:
        _clear_jobs(db)
        now = datetime.now(timezone.utc)
        pre_sent = now - timedelta(days=2)
        notice_id = "notice-456"
        profile = _create_profile(
            db,
            in_dispute=True,
            pre_adverse_sent_at=pre_sent,
            notice_id=notice_id,
        )

        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        resumed, scheduled_for = await workflow.resolve_dispute_and_resume_final_adverse(profile.id)
        db.flush()

        assert resumed is False
        assert scheduled_for is not None

        holidays = _holidays_for(pre_sent)
        expected_ready = add_us_business_days(pre_sent, 5, holidays)
        assert scheduled_for == expected_ready

        jobs = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.type == FINAL_ADVERSE_JOB_TYPE)
            .all()
        )
        assert len(jobs) == 1
        job = jobs[0]
        assert job.available_at == expected_ready

        db.refresh(profile)
        assert profile.bgc_in_dispute is False
        assert profile.bgc_dispute_resolved_at is not None
    finally:
        settings.is_testing = original_testing


@pytest.mark.anyio
async def test_resume_final_adverse_noop_when_final_already_sent(db: Session) -> None:
    original_testing = settings.is_testing
    settings.is_testing = False
    try:
        _clear_jobs(db)
        now = datetime.now(timezone.utc)
        profile = _create_profile(
            db,
            in_dispute=True,
            pre_adverse_sent_at=now - timedelta(days=7),
            notice_id="notice-789",
            final_sent_at=now - timedelta(days=1),
        )

        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        resumed, scheduled_for = await workflow.resolve_dispute_and_resume_final_adverse(profile.id)
        db.flush()

        assert resumed is False
        assert scheduled_for is None

        jobs = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.type == FINAL_ADVERSE_JOB_TYPE)
            .all()
        )
        assert len(jobs) == 0

        db.refresh(profile)
        assert profile.bgc_in_dispute is False
        assert profile.bgc_dispute_resolved_at is not None
    finally:
        settings.is_testing = original_testing
