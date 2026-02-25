"""
Tests for app/tasks/email.py - targeting CI coverage gaps.

This module tests the send_beta_invites_batch Celery task.

Note: Dead code (booking confirmation, reminder, cancellation, password reset tasks)
was removed. Those functions are handled by NotificationService and PasswordResetService.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestSendBetaInvitesBatchTask:
    """Tests for send_beta_invites_batch task."""

    def test_task_is_registered(self):
        """Test that send_beta_invites_batch task is registered."""
        from app.tasks.email import send_beta_invites_batch

        assert send_beta_invites_batch.name == "app.tasks.email.send_beta_invites_batch"

    def test_task_has_max_retries(self):
        """Test that task has proper retry config."""
        from app.tasks.email import send_beta_invites_batch

        assert send_beta_invites_batch.max_retries == 2

    def test_task_is_bound(self):
        """Test that task is bound (has access to self)."""
        from app.tasks.email import send_beta_invites_batch

        # Bound tasks have __wrapped__ attribute
        assert hasattr(send_beta_invites_batch, "__wrapped__")

    def test_task_in_email_namespace(self):
        """Test that task is in the email namespace."""
        from app.tasks.email import send_beta_invites_batch

        assert "email" in send_beta_invites_batch.name

    @patch("app.tasks.email.get_db")
    @patch("app.tasks.email.BetaService")
    @patch("celery.current_task", None)
    def test_empty_emails_list_returns_success(self, mock_beta_service, mock_get_db):
        """Test handling of empty emails list."""
        from app.tasks.email import send_beta_invites_batch

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_service = MagicMock()
        mock_beta_service.return_value = mock_service

        result = send_beta_invites_batch(
            emails=[],
            role="student",
            expires_in_days=7,
            source="test",
            base_url="https://example.com",
        )

        assert result["status"] == "success"
        # Note: sent/failed are lists due to **results spread at end of return dict
        assert len(result["sent"]) == 0
        assert len(result["failed"]) == 0
        assert result["total"] == 0
        mock_db.close.assert_called_once()

    @patch("app.tasks.email.get_db")
    @patch("app.tasks.email.BetaService")
    @patch("celery.current_task", None)
    def test_successful_batch_send(self, mock_beta_service, mock_get_db):
        """Test successful batch email sending."""
        from app.tasks.email import send_beta_invites_batch

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_invite = Mock()
        mock_invite.id = "invite-1"
        mock_invite.code = "CODE123"

        mock_service = MagicMock()
        mock_service.send_invite_email.return_value = (
            mock_invite,
            "https://join.url",
            "https://welcome.url",
        )
        mock_beta_service.return_value = mock_service

        result = send_beta_invites_batch(
            emails=["user1@example.com", "user2@example.com"],
            role="student",
            expires_in_days=7,
            source="test",
            base_url="https://example.com",
        )

        assert result["status"] == "success"
        # Note: sent/failed are lists due to **results spread at end of return dict
        assert len(result["sent"]) == 2
        assert len(result["failed"]) == 0
        assert mock_service.send_invite_email.call_count == 2
        mock_db.close.assert_called_once()

    @patch("app.tasks.email.get_db")
    @patch("app.tasks.email.BetaService")
    @patch("celery.current_task", None)
    def test_partial_failure_handling(self, mock_beta_service, mock_get_db):
        """Test handling when some emails fail to send."""
        from app.tasks.email import send_beta_invites_batch

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_invite = Mock()
        mock_invite.id = "invite-1"
        mock_invite.code = "CODE123"

        call_count = [0]

        def send_invite_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # Second call fails
                raise Exception("SMTP error")
            return mock_invite, "https://join.url", "https://welcome.url"

        mock_service = MagicMock()
        mock_service.send_invite_email.side_effect = send_invite_effect
        mock_beta_service.return_value = mock_service

        result = send_beta_invites_batch(
            emails=["user1@example.com", "fail@example.com", "user3@example.com"],
            role="student",
            expires_in_days=7,
            source="test",
            base_url="https://example.com",
        )

        # Note: sent/failed are lists due to **results spread at end of return dict
        assert len(result["sent"]) == 2
        assert len(result["failed"]) == 1
        assert result["failed"][0]["email"] == "fail@example.com"
        mock_db.close.assert_called_once()

    @patch("app.tasks.email.get_db")
    @patch("app.tasks.email.BetaService")
    def test_progress_updates_when_current_task_exists(self, mock_beta_service, mock_get_db):
        """Test that task updates progress when current_task is available."""
        from app.tasks.email import send_beta_invites_batch

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_invite = Mock()
        mock_invite.id = "invite-1"
        mock_invite.code = "CODE123"

        mock_service = MagicMock()
        mock_service.send_invite_email.return_value = (
            mock_invite,
            "https://join.url",
            "https://welcome.url",
        )
        mock_beta_service.return_value = mock_service

        mock_current_task = MagicMock()

        # Patch at the celery module level since the import happens inside the function
        with patch("celery.current_task", mock_current_task):
            send_beta_invites_batch(
                emails=["user1@example.com", "user2@example.com"],
                role="student",
                expires_in_days=7,
                source="test",
                base_url="https://example.com",
            )

        # Should have called update_state for each email
        assert mock_current_task.update_state.call_count == 2

        # Verify progress state format
        call_args = mock_current_task.update_state.call_args_list
        assert call_args[0][1]["state"] == "PROGRESS"
        assert call_args[0][1]["meta"]["current"] == 1
        assert call_args[1][1]["meta"]["current"] == 2

    @patch("app.tasks.email.get_db")
    @patch("app.tasks.email.BetaService")
    @patch("celery.current_task", None)
    def test_result_includes_invite_details(self, mock_beta_service, mock_get_db):
        """Test that successful results include invite details."""
        from app.tasks.email import send_beta_invites_batch

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_invite = Mock()
        mock_invite.id = "01ABC123"
        mock_invite.code = "BETA2024"

        mock_service = MagicMock()
        mock_service.send_invite_email.return_value = (
            mock_invite,
            "https://join.example.com/BETA2024",
            "https://welcome.example.com",
        )
        mock_beta_service.return_value = mock_service

        result = send_beta_invites_batch(
            emails=["test@example.com"],
            role="instructor",
            expires_in_days=14,
            source="admin",
            base_url="https://example.com",
        )

        assert len(result["sent"]) == 1
        sent_item = result["sent"][0]
        assert sent_item["id"] == "01ABC123"
        assert sent_item["code"] == "BETA2024"
        assert sent_item["email"] == "test@example.com"
        assert sent_item["join_url"] == "https://join.example.com/BETA2024"


    @patch("app.tasks.email.get_db")
    @patch("app.tasks.email.BetaService")
    @patch("celery.current_task", None)
    def test_outer_exception_triggers_retry(self, mock_beta_service, mock_get_db):
        """L98-99: Exception during BetaService init triggers self.retry."""
        from app.tasks.email import send_beta_invites_batch

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_beta_service.side_effect = RuntimeError("service init failed")

        # The task is bound, so self.retry will be called.
        # self.retry raises Retry exception by default.
        from celery.exceptions import Retry

        with patch.object(send_beta_invites_batch, "retry", side_effect=Retry("retry")) as mock_retry:
            with pytest.raises(Retry):
                send_beta_invites_batch(
                    emails=["test@example.com"],
                    role="student",
                    expires_in_days=7,
                    source="test",
                    base_url="https://example.com",
                )
            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args
            assert call_kwargs[1]["countdown"] == 60
        mock_db.close.assert_called_once()


class TestEmailModuleImports:
    """Tests for email module imports."""

    def test_module_imports_successfully(self):
        """Verify email.py imports without errors (regression for fixed import bug)."""
        # This test verifies the import bug was fixed
        # Previously: from app.core.database import get_db (WRONG)
        # Now: from app.database import get_db (CORRECT)
        from app.tasks import email

        assert email is not None
        assert hasattr(email, "send_beta_invites_batch")

    def test_get_db_import_is_correct(self):
        """Verify get_db is imported from the correct module."""
        from app.database import get_db as correct_get_db
        from app.tasks import email

        # The email module should use the same get_db function
        assert email.get_db is correct_get_db
