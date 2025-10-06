from app.core.config import settings
from app.database import SessionLocal
from app.models.instructor import BackgroundJob
from app.repositories.background_job_repository import BackgroundJobRepository


def test_mark_failed_moves_job_to_dlq_when_attempts_exhausted():
    original_max_attempts = getattr(settings, "jobs_max_attempts", 5)
    settings.jobs_max_attempts = 3

    session = SessionLocal()
    job_id = None
    try:
        repo = BackgroundJobRepository(session)
        job_id = repo.enqueue(type="test.dead_letter", payload={})
        session.commit()

        # First two failures should reschedule the job
        for attempt in range(2):
            terminal = repo.mark_failed(job_id, f"error-{attempt}")
            session.commit()
            assert terminal is False
            job = session.get(BackgroundJob, job_id)
            assert job.status == "queued"
            assert job.attempts == attempt + 1
            assert job.available_at is not None

        # Third failure should mark the job as failed (dead-letter)
        terminal = repo.mark_failed(job_id, "fatal-error")
        session.commit()
        assert terminal is True

        job = session.get(BackgroundJob, job_id)
        assert job.status == "failed"
        assert job.available_at == job.updated_at
        assert job.attempts == 3
        assert job.last_error == "fatal-error"
    finally:
        # Clean up persisted job and restore settings
        if job_id is not None:
            job = session.get(BackgroundJob, job_id)
            if job is not None:
                session.delete(job)
                session.commit()
        session.close()
        settings.jobs_max_attempts = original_max_attempts
