"""
Unit tests for InstructorProfileRepository BGC methods - targeting CI coverage gaps.

Focus on uncovered lines: 568-573, 714-721, 754-811, 831-858
- Error handling in get_by_report_id
- Error handling in bind_report_to_candidate
- bind_report_to_invitation
- update_valid_until
- set_bgc_invited_at
- set_pre_adverse_notice
- mark_review_email_sent
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.instructor_profile_repository import InstructorProfileRepository


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = None
    db.update.return_value = 1
    db.flush = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def repository(mock_db):
    """Create repository with mock db."""
    return InstructorProfileRepository(mock_db)


class TestGetByReportIdErrorHandling:
    """Tests for get_by_report_id error handling (lines 567-573)."""

    def test_get_by_report_id_sqlalchemy_error(self, mock_db, repository):
        """Test that SQLAlchemy errors are caught and re-raised as RepositoryException."""
        mock_db.query.side_effect = SQLAlchemyError("Connection failed")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="Failed to look up instructor by report id"):
            repository.get_by_report_id("report-123")

    def test_get_by_report_id_logs_error(self, mock_db, repository, caplog):
        """Test that errors are logged properly."""
        mock_db.query.side_effect = SQLAlchemyError("Database error")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException):
            repository.get_by_report_id("report-456")

        # Verify error was logged (actual log message includes "Failed resolving report")
        assert any("Failed resolving report" in record.message for record in caplog.records)


class TestBindReportToCandidateErrorHandling:
    """Tests for bind_report_to_candidate error handling (lines 714-721)."""

    def test_bind_report_to_candidate_sqlalchemy_error(self, mock_db, repository):
        """Test SQLAlchemy error handling in bind_report_to_candidate."""
        mock_db.query.return_value.filter.side_effect = SQLAlchemyError("Query failed")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="Failed to bind report to candidate"):
            repository.bind_report_to_candidate(
                candidate_id="cand-123",
                report_id="report-456",
                env="production",
            )

    def test_bind_report_to_candidate_logs_error(self, mock_db, repository, caplog):
        """Test that errors are logged with candidate and report IDs."""
        mock_db.query.return_value.filter.side_effect = SQLAlchemyError("DB error")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException):
            repository.bind_report_to_candidate(
                candidate_id="cand-789",
                report_id="report-abc",
            )

        assert any("cand-789" in record.message for record in caplog.records)


class TestBindReportToInvitation:
    """Tests for bind_report_to_invitation method (lines 754-773)."""

    def test_bind_report_to_invitation_success(self, mock_db, repository):
        """Test successful binding via invitation."""
        mock_profile = MagicMock()
        mock_profile.id = "instructor-123"
        mock_profile.bgc_report_id = None
        mock_profile.bgc_env = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        result = repository.bind_report_to_invitation(
            invitation_id="inv-123",
            report_id="report-456",
            env="sandbox",
        )

        assert result == "instructor-123"
        assert mock_profile.bgc_report_id == "report-456"
        assert mock_profile.bgc_env == "sandbox"
        mock_db.flush.assert_called_once()

    def test_bind_report_to_invitation_not_found(self, mock_db, repository):
        """Test when no profile found for invitation."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = repository.bind_report_to_invitation(
            invitation_id="inv-unknown",
            report_id="report-123",
        )

        assert result is None

    def test_bind_report_to_invitation_sqlalchemy_error(self, mock_db, repository):
        """Test SQLAlchemy error handling."""
        mock_db.query.return_value.filter.side_effect = SQLAlchemyError("Query failed")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="Failed to bind report to invitation"):
            repository.bind_report_to_invitation(
                invitation_id="inv-123",
                report_id="report-456",
            )

    def test_bind_report_to_invitation_skips_update_if_same(self, mock_db, repository):
        """Test that update is skipped if report_id already matches."""
        mock_profile = MagicMock()
        mock_profile.id = "instructor-123"
        mock_profile.bgc_report_id = "report-456"  # Already set
        mock_profile.bgc_env = "sandbox"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        result = repository.bind_report_to_invitation(
            invitation_id="inv-123",
            report_id="report-456",  # Same as existing
            env="sandbox",
        )

        assert result == "instructor-123"
        # report_id should not be updated (already the same)


class TestUpdateValidUntil:
    """Tests for update_valid_until method (lines 775-792)."""

    def test_update_valid_until_success(self, mock_db, repository):
        """Test successful update of bgc_valid_until."""
        mock_profile = MagicMock()

        valid_until = datetime.now(timezone.utc)
        with patch.object(repository, "get_by_id", return_value=mock_profile):
            repository.update_valid_until("instructor-123", valid_until)

        assert mock_profile.bgc_valid_until == valid_until
        mock_db.flush.assert_called_once()

    def test_update_valid_until_not_found(self, repository):
        """Test error when instructor not found."""
        with patch.object(repository, "get_by_id", return_value=None):
            from app.core.exceptions import RepositoryException

            with pytest.raises(RepositoryException, match="not found"):
                repository.update_valid_until("unknown-123", datetime.now(timezone.utc))

    def test_update_valid_until_sqlalchemy_error(self, mock_db, repository):
        """Test SQLAlchemy error handling with rollback."""
        mock_profile = MagicMock()

        def raise_on_flush():
            raise SQLAlchemyError("Flush failed")

        mock_db.flush.side_effect = raise_on_flush

        with patch.object(repository, "get_by_id", return_value=mock_profile):
            from app.core.exceptions import RepositoryException

            with pytest.raises(RepositoryException, match="Failed to update background check validity"):
                repository.update_valid_until("instructor-123", datetime.now(timezone.utc))

        mock_db.rollback.assert_called_once()


class TestSetBgcInvitedAt:
    """Tests for set_bgc_invited_at method (lines 794-811)."""

    def test_set_bgc_invited_at_success(self, mock_db, repository):
        """Test successful setting of bgc_invited_at."""
        mock_profile = MagicMock()

        invited_at = datetime.now(timezone.utc)
        with patch.object(repository, "get_by_id", return_value=mock_profile):
            repository.set_bgc_invited_at("instructor-123", invited_at)

        assert mock_profile.bgc_invited_at == invited_at
        mock_db.flush.assert_called_once()

    def test_set_bgc_invited_at_not_found(self, repository):
        """Test error when instructor not found."""
        with patch.object(repository, "get_by_id", return_value=None):
            from app.core.exceptions import RepositoryException

            with pytest.raises(RepositoryException, match="not found"):
                repository.set_bgc_invited_at("unknown-123", datetime.now(timezone.utc))


def test_update_bgc_by_invitation_updates_fields(mock_db, repository):
    profile = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = profile

    result = repository.update_bgc_by_invitation(
        "invite-1",
        status="pending",
        note="waiting",
    )

    assert result == profile
    assert profile.bgc_status == "pending"
    assert profile.bgc_note == "waiting"
    mock_db.flush.assert_called_once()


def test_update_bgc_by_candidate_updates_fields(mock_db, repository):
    profile = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = profile

    result = repository.update_bgc_by_candidate(
        "candidate-1",
        status="clear",
        note="ok",
    )

    assert result == profile
    assert profile.bgc_status == "clear"
    assert profile.bgc_note == "ok"
    mock_db.flush.assert_called_once()


def test_update_bgc_by_report_id_returns_zero_when_missing(repository):
    with patch.object(repository, "_resolve_profile_id_by_report", return_value=None):
        assert repository.update_bgc_by_report_id("report-1") == 0


def test_update_eta_by_report_id_returns_zero_when_profile_missing(repository):
    with patch.object(repository, "_resolve_profile_id_by_report", return_value="profile-1"):
        with patch.object(repository, "get_by_id", return_value=None):
            assert repository.update_eta_by_report_id("report-1", datetime.now(timezone.utc)) == 0


def test_record_adverse_event_sqlalchemy_error(mock_db, repository):
    mock_db.flush.side_effect = SQLAlchemyError("flush failed")

    from app.core.exceptions import RepositoryException

    with pytest.raises(RepositoryException, match="Failed to record adverse-action event"):
        repository.record_adverse_event("instructor-1", "notice-1", "pre_adverse")


def test_has_adverse_event_sqlalchemy_error(mock_db, repository):
    mock_db.query.side_effect = SQLAlchemyError("query failed")

    from app.core.exceptions import RepositoryException

    with pytest.raises(RepositoryException, match="Failed to check adverse-action event"):
        repository.has_adverse_event("instructor-1", "notice-1", "pre_adverse")


def test_set_dispute_open_not_found(mock_db, repository):
    mock_db.query.return_value.filter.return_value.update.return_value = 0

    from app.core.exceptions import RepositoryException

    with pytest.raises(RepositoryException, match="not found"):
        repository.set_dispute_open("instructor-1", note=None)

    def test_set_bgc_invited_at_sqlalchemy_error(self, mock_db, repository):
        """Test SQLAlchemy error handling with rollback."""
        mock_profile = MagicMock()

        mock_db.flush.side_effect = SQLAlchemyError("Flush failed")

        with patch.object(repository, "get_by_id", return_value=mock_profile):
            from app.core.exceptions import RepositoryException

            with pytest.raises(RepositoryException, match="Failed to update background check invite timestamp"):
                repository.set_bgc_invited_at("instructor-123", datetime.now(timezone.utc))

        mock_db.rollback.assert_called_once()


class TestSetPreAdverseNotice:
    """Tests for set_pre_adverse_notice method (lines 813-837)."""

    def test_set_pre_adverse_notice_success(self, mock_db, repository):
        """Test successful setting of pre-adverse notice."""
        mock_db.query.return_value.filter.return_value.update.return_value = 1

        sent_at = datetime.now(timezone.utc)
        repository.set_pre_adverse_notice(
            instructor_id="instructor-123",
            notice_id="notice-456",
            sent_at=sent_at,
        )

        mock_db.flush.assert_called_once()

    def test_set_pre_adverse_notice_not_found(self, mock_db, repository):
        """Test error when instructor not found (update returns 0)."""
        mock_db.query.return_value.filter.return_value.update.return_value = 0

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="not found"):
            repository.set_pre_adverse_notice(
                instructor_id="unknown-123",
                notice_id="notice-456",
                sent_at=datetime.now(timezone.utc),
            )

    def test_set_pre_adverse_notice_sqlalchemy_error(self, mock_db, repository):
        """Test SQLAlchemy error handling with rollback."""
        mock_db.query.return_value.filter.return_value.update.side_effect = SQLAlchemyError("Update failed")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="Failed to persist pre-adverse metadata"):
            repository.set_pre_adverse_notice(
                instructor_id="instructor-123",
                notice_id="notice-456",
                sent_at=datetime.now(timezone.utc),
            )

        mock_db.rollback.assert_called_once()


class TestMarkReviewEmailSent:
    """Tests for mark_review_email_sent method (lines 839-858)."""

    def test_mark_review_email_sent_success(self, mock_db, repository):
        """Test successful marking of review email sent."""
        mock_db.query.return_value.filter.return_value.update.return_value = 1

        sent_at = datetime.now(timezone.utc)
        repository.mark_review_email_sent("instructor-123", sent_at)

        mock_db.flush.assert_called_once()

    def test_mark_review_email_sent_not_found(self, mock_db, repository):
        """Test error when instructor not found."""
        mock_db.query.return_value.filter.return_value.update.return_value = 0

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="not found"):
            repository.mark_review_email_sent("unknown-123", datetime.now(timezone.utc))

    def test_mark_review_email_sent_sqlalchemy_error(self, mock_db, repository):
        """Test SQLAlchemy error handling with rollback."""
        mock_db.query.return_value.filter.return_value.update.side_effect = SQLAlchemyError("Update failed")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException, match="Failed to persist review email metadata"):
            repository.mark_review_email_sent(
                instructor_id="instructor-123",
                sent_at=datetime.now(timezone.utc),
            )

        mock_db.rollback.assert_called_once()

    def test_mark_review_email_sent_logs_error(self, mock_db, repository, caplog):
        """Test that errors are logged properly."""
        mock_db.query.return_value.filter.return_value.update.side_effect = SQLAlchemyError("DB error")

        from app.core.exceptions import RepositoryException

        with pytest.raises(RepositoryException):
            repository.mark_review_email_sent("instructor-xyz", datetime.now(timezone.utc))

        assert any("instructor-xyz" in record.message for record in caplog.records)
