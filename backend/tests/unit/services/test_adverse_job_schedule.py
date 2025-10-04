from datetime import date, datetime, timezone
from typing import cast

from sqlalchemy.orm import Session
from tests.unit.services._adverse_helpers import ensure_adverse_schema
import ulid

from app.core.config import settings
from app.models.instructor import BackgroundJob, InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import (
    FINAL_ADVERSE_JOB_TYPE,
    BackgroundCheckWorkflowService,
    FinalAdversePayload,
)
from app.utils.business_days import add_us_business_days, us_federal_holidays


def _holidays_for_years(start_year: int) -> set[date]:
    return (
        us_federal_holidays(start_year - 1)
        | us_federal_holidays(start_year)
        | us_federal_holidays(start_year + 1)
    )


def _create_instructor(db: Session) -> InstructorProfile:
    ensure_adverse_schema(db)

    user = User(
        email="adverse-job@example.com",
        hashed_password="hashed",
        first_name="Pre",
        last_name="Adverse",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = "review"
    db.add(profile)
    db.flush()
    return profile


def test_schedule_enqueues_single_job(db: Session) -> None:
    original_testing = settings.is_testing
    settings.is_testing = False
    try:
        profile = _create_instructor(db)
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        sent_at = datetime(2024, 3, 6, 12, 0, tzinfo=timezone.utc)
        notice_id = str(ulid.ULID())
        repo.set_pre_adverse_notice(profile.id, notice_id, sent_at)
        db.flush()

        workflow.schedule_final_adverse_action(profile.id)
        workflow.schedule_final_adverse_action(profile.id)

        matching_jobs: list[tuple[BackgroundJob, FinalAdversePayload]] = []
        for job in db.query(BackgroundJob).filter(BackgroundJob.type == FINAL_ADVERSE_JOB_TYPE).all():
            payload_raw = job.payload
            if not isinstance(payload_raw, dict):
                continue
            payload = cast(FinalAdversePayload, payload_raw)
            if payload["profile_id"] == profile.id:
                matching_jobs.append((job, payload))

        assert len(matching_jobs) == 1
        job, payload = matching_jobs[0]

        holidays = _holidays_for_years(sent_at.year)
        expected_available = add_us_business_days(sent_at, 5, holidays)

        assert job.available_at == expected_available
        assert payload["profile_id"] == profile.id
        assert payload["pre_adverse_notice_id"] == notice_id
        assert payload["pre_adverse_sent_at"] == sent_at.isoformat()
    finally:
        settings.is_testing = original_testing
