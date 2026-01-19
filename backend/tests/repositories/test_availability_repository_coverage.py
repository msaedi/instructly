from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.models.availability import BlackoutDate
from app.repositories.availability_repository import AvailabilityRepository


def test_get_future_blackout_dates(db, monkeypatch, test_instructor):
    repo = AvailabilityRepository(db)
    instructor_id = test_instructor.id
    today = date.today()

    blackout = BlackoutDate(instructor_id=instructor_id, date=today, reason="trip")
    db.add(blackout)
    db.commit()

    monkeypatch.setattr(
        "app.repositories.availability_repository.get_user_today_by_id",
        lambda _id, _db: today - timedelta(days=1),
    )

    rows = repo.get_future_blackout_dates(instructor_id)
    assert rows[0].id == blackout.id


def test_create_and_delete_blackout_date(db, test_instructor_2):
    repo = AvailabilityRepository(db)
    instructor_id = test_instructor_2.id
    day = date.today() + timedelta(days=1)

    blackout = repo.create_blackout_date(instructor_id, day, reason="vacation")
    assert blackout.reason == "vacation"

    deleted = repo.delete_blackout_date(blackout.id, instructor_id)
    assert deleted is True


def test_create_blackout_date_duplicate(db, test_instructor):
    repo = AvailabilityRepository(db)
    instructor_id = test_instructor.id
    day = date.today() + timedelta(days=1)

    repo.create_blackout_date(instructor_id, day)

    with pytest.raises(Exception):
        repo.create_blackout_date(instructor_id, day)


def test_delete_blackout_date_missing_and_flush(db, test_instructor):
    repo = AvailabilityRepository(db)
    assert repo.delete_blackout_date("missing", test_instructor.id) is False
    repo.flush()


def test_get_future_blackout_dates_error(db, test_instructor, monkeypatch):
    repo = AvailabilityRepository(db)

    def _raise(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "query", _raise)

    with pytest.raises(RepositoryException):
        repo.get_future_blackout_dates(test_instructor.id)
