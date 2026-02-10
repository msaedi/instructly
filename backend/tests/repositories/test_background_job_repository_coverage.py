from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models.instructor import BackgroundJob
from app.repositories.background_job_repository import BackgroundJobRepository


def test_enqueue_and_fetch_due(db):
    repo = BackgroundJobRepository(db)
    job_id = repo.enqueue(
        type="job.test",
        payload={"a": 1},
        available_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    db.commit()

    jobs = repo.fetch_due(limit=10)
    assert any(job.id == job_id for job in jobs)


def test_mark_running_and_succeeded(db):
    repo = BackgroundJobRepository(db)
    job_id = repo.enqueue(type="job.test", payload={"a": 1})
    db.commit()

    repo.mark_running(job_id)
    repo.mark_succeeded(job_id)
    db.commit()

    row = db.get(BackgroundJob, job_id)
    assert row.status == "succeeded"


def test_mark_failed_reschedules_and_terminal(db, monkeypatch):
    monkeypatch.setattr(settings, "jobs_max_attempts", 2, raising=False)
    monkeypatch.setattr(settings, "jobs_backoff_base", 1, raising=False)
    monkeypatch.setattr(settings, "jobs_backoff_cap", 2, raising=False)

    repo = BackgroundJobRepository(db)
    job_id = repo.enqueue(type="job.test", payload={"a": 1})
    db.commit()

    terminal = repo.mark_failed(job_id, "boom")
    db.commit()
    row = db.get(BackgroundJob, job_id)
    assert terminal is False
    assert row.status == "queued"

    terminal = repo.mark_failed(job_id, "boom")
    db.commit()
    row = db.get(BackgroundJob, job_id)
    assert terminal is True
    assert row.status == "failed"


def test_mark_failed_missing_job(db):
    repo = BackgroundJobRepository(db)
    assert repo.mark_failed("missing", "err") is False


def test_count_failed_jobs_and_next_scheduled(db):
    repo = BackgroundJobRepository(db)
    job_id = repo.enqueue(type="job.test", payload={"a": 1})
    db.commit()

    repo.mark_failed(job_id, "boom")
    db.commit()

    assert repo.count_failed_jobs() >= 0

    job_type = f"job.next.{generate_ulid()}"
    job_id = repo.enqueue(type=job_type, payload={"a": 1})
    db.commit()

    job = repo.get_next_scheduled(job_type)
    assert job is not None
    assert job.id == job_id


def test_get_pending_final_adverse_job(db):
    repo = BackgroundJobRepository(db)
    payload = {
        "profile_id": f"profile-{generate_ulid()}",
        "pre_adverse_notice_id": f"notice-{generate_ulid()}",
    }
    job_id = repo.enqueue(
        type="background_check.final_adverse_action", payload=payload
    )
    db.commit()

    job = repo.get_pending_final_adverse_job(
        payload["profile_id"], payload["pre_adverse_notice_id"]
    )
    assert job is not None
    assert job.id == job_id


def test_repository_errors_raise(db, monkeypatch):
    repo = BackgroundJobRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)

    with pytest.raises(RepositoryException):
        repo.fetch_due()
    with pytest.raises(RepositoryException):
        repo.mark_running("job")
    with pytest.raises(RepositoryException):
        repo.mark_succeeded("job")
    with pytest.raises(RepositoryException):
        repo.count_failed_jobs()
    with pytest.raises(RepositoryException):
        repo.get_next_scheduled("job")
    with pytest.raises(RepositoryException):
        repo.get_pending_final_adverse_job("profile", "notice")


def test_mark_failed_error(db, monkeypatch):
    repo = BackgroundJobRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "get", _raise)

    with pytest.raises(RepositoryException):
        repo.mark_failed("job", "err")


def test_mark_terminal_failure_paths(db, monkeypatch):
    monkeypatch.setattr(settings, "jobs_max_attempts", 3, raising=False)
    repo = BackgroundJobRepository(db)

    # Missing job is a no-op.
    repo.mark_terminal_failure("missing", "boom")

    # Existing job is marked failed and attempts set to max.
    job_id = repo.enqueue(type="job.terminal", payload={"x": 1})
    db.commit()
    repo.mark_terminal_failure(job_id, "fatal")
    db.commit()

    row = db.get(BackgroundJob, job_id)
    assert row is not None
    assert row.status == "failed"
    assert row.attempts == 3
    assert row.last_error == "fatal"


def test_mark_terminal_failure_error_raises(db, monkeypatch):
    repo = BackgroundJobRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "get", _raise)
    with pytest.raises(RepositoryException):
        repo.mark_terminal_failure("job", "fatal")


def test_enqueue_and_pending_final_adverse_edge_cases(db, monkeypatch):
    repo = BackgroundJobRepository(db)

    # Non-dict payload rows should be ignored when matching.
    repo.enqueue(
        type="background_check.final_adverse_action",
        payload="not-a-dict",
    )
    target_payload = {
        "profile_id": "profile-x",
        "pre_adverse_notice_id": "notice-y",
    }
    repo.enqueue(
        type="background_check.final_adverse_action",
        payload=target_payload,
    )
    db.commit()

    job = repo.get_pending_final_adverse_job("profile-x", "notice-y")
    assert job is not None
    assert job.type == "background_check.final_adverse_action"
    assert isinstance(job.payload, dict)
    assert job.payload["profile_id"] == "profile-x"
    assert job.payload["pre_adverse_notice_id"] == "notice-y"

    def _raise_add(*_args, **_kwargs):
        raise SQLAlchemyError("enqueue-boom")

    monkeypatch.setattr(repo.db, "add", _raise_add)
    with pytest.raises(RepositoryException):
        repo.enqueue(type="job.fail", payload={})
