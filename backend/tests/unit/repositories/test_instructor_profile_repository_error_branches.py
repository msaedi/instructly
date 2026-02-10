"""Error-branch coverage tests for InstructorProfileRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.instructor_profile_repository import InstructorProfileRepository


def _repo():
    db = MagicMock()
    return InstructorProfileRepository(db), db


def test_get_by_report_id_query_error_raises_repository_exception():
    repo, db = _repo()
    repo._resolve_profile_id_by_report = MagicMock(return_value="profile-id")
    db.query.side_effect = SQLAlchemyError("boom")

    with pytest.raises(RepositoryException):
        repo.get_by_report_id("rpt_123")


def test_set_bgc_invited_at_flush_error_rolls_back():
    repo, db = _repo()
    repo.get_by_id = MagicMock(return_value=SimpleNamespace())
    db.flush.side_effect = SQLAlchemyError("flush failed")

    with pytest.raises(RepositoryException):
        repo.set_bgc_invited_at("profile-id", datetime.now(timezone.utc))

    db.rollback.assert_called_once()


def test_set_final_adverse_sent_at_query_error_rolls_back():
    repo, db = _repo()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value.update.side_effect = SQLAlchemyError("update failed")

    with pytest.raises(RepositoryException):
        repo.set_final_adverse_sent_at("profile-id", datetime.now(timezone.utc))

    db.rollback.assert_called_once()


def test_set_dispute_resolved_missing_profile_raises_repository_exception():
    repo, db = _repo()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value.update.return_value = 0

    with pytest.raises(RepositoryException):
        repo.set_dispute_resolved("missing-profile", "resolved-note")


def test_set_live_missing_profile_raises_repository_exception():
    repo, db = _repo()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value.update.return_value = 0

    with pytest.raises(RepositoryException):
        repo.set_live("missing-profile", True)


def test_list_expiring_within_query_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = SQLAlchemyError("query failed")

    with pytest.raises(RepositoryException):
        repo.list_expiring_within(days=30)


def test_list_expired_query_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = SQLAlchemyError("query failed")

    with pytest.raises(RepositoryException):
        repo.list_expired()


def test_append_history_add_error_raises_repository_exception():
    repo, db = _repo()
    db.add.side_effect = SQLAlchemyError("add failed")

    with pytest.raises(RepositoryException):
        repo.append_history(
            instructor_id="profile-id",
            report_id="rpt_1",
            result="passed",
            package="basic",
            env="sandbox",
            completed_at=datetime.now(timezone.utc),
        )

    db.rollback.assert_called_once()


def test_get_history_query_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = SQLAlchemyError("query failed")

    with pytest.raises(RepositoryException):
        repo.get_history("profile-id")


def test_record_bgc_consent_add_error_raises_repository_exception():
    repo, db = _repo()
    db.add.side_effect = SQLAlchemyError("add failed")

    with pytest.raises(RepositoryException):
        repo.record_bgc_consent(
            "profile-id",
            consent_version="v1",
            ip_address="127.0.0.1",
        )

    db.rollback.assert_called_once()


def test_has_recent_consent_sqlalchemy_error_raises_repository_exception():
    repo, _db = _repo()
    repo.latest_consent = MagicMock(side_effect=SQLAlchemyError("read failed"))

    with pytest.raises(RepositoryException):
        repo.has_recent_consent("profile-id", window=timedelta(days=1))


def test_find_by_filters_generic_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.find_by_filters(search="piano")


def test_find_by_service_ids_generic_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.find_by_service_ids(["svc-1"])


def test_find_profile_ids_by_report_fragment_query_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = SQLAlchemyError("query failed")

    with pytest.raises(RepositoryException):
        repo.find_profile_ids_by_report_fragment("fragment")


def test_resolve_profile_id_by_report_query_error_raises_repository_exception():
    repo, db = _repo()
    db.query.side_effect = SQLAlchemyError("query failed")

    with pytest.raises(RepositoryException):
        repo._resolve_profile_id_by_report("rpt_1")


def test_encrypt_report_id_passthrough_does_not_increment_metric():
    with patch(
        "app.repositories.instructor_profile_repository.encrypt_report_token",
        return_value="rpt_123",
    ):
        with patch(
            "app.repositories.instructor_profile_repository.BGC_REPORT_ID_ENCRYPT_TOTAL"
        ) as metric:
            encrypted = InstructorProfileRepository._encrypt_report_id("rpt_123")

    assert encrypted == "rpt_123"
    metric.labels.return_value.inc.assert_not_called()
