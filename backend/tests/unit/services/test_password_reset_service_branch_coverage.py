from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest

from app.core.exceptions import ValidationException
from app.services.password_reset_service import PasswordResetService


def _make_service() -> tuple[PasswordResetService, MagicMock, MagicMock, MagicMock]:
    db = MagicMock()
    user_repo = MagicMock()
    token_repo = MagicMock()
    email_service = MagicMock()
    service = PasswordResetService(
        db=db,
        cache_service=MagicMock(),
        email_service=email_service,
        user_repository=user_repo,
        token_repository=token_repo,
    )
    return service, db, user_repo, token_repo


def test_init_creates_default_email_service_when_not_injected() -> None:
    db = MagicMock()
    user_repo = MagicMock()
    token_repo = MagicMock()
    built_email_service = MagicMock()

    with patch("app.services.password_reset_service.EmailService", return_value=built_email_service) as email_cls:
        service = PasswordResetService(
            db=db,
            cache_service=MagicMock(),
            email_service=None,
            user_repository=user_repo,
            token_repository=token_repo,
        )

    email_cls.assert_called_once_with(db, ANY)
    assert service.email_service is built_email_service


def test_verify_reset_token_returns_invalid_when_user_not_found() -> None:
    service, _, user_repo, token_repo = _make_service()
    token_repo.find_one_by.return_value = SimpleNamespace(
        user_id="user_1",
        token="tok_1",
        used=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    user_repo.get_by_id.return_value = None

    assert service.verify_reset_token("tok_1") == (False, None)


def test_confirm_password_reset_rejects_token_without_user() -> None:
    service, _, user_repo, token_repo = _make_service()
    token_repo.find_one_by.return_value = SimpleNamespace(
        id="prt_1",
        user_id="missing_user",
        token="tok_2",
        used=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    user_repo.get_by_id.return_value = None

    with pytest.raises(ValidationException, match="Invalid reset token"):
        service.confirm_password_reset("tok_2", "NewPassword123!")


def test_confirm_password_reset_wraps_unexpected_errors() -> None:
    service, db, user_repo, token_repo = _make_service()
    token_repo.find_one_by.return_value = SimpleNamespace(
        id="prt_2",
        user_id="user_2",
        token="tok_3",
        used=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    user_repo.get_by_id.return_value = SimpleNamespace(
        id="user_2",
        email="user2@example.com",
        first_name="Casey",
    )
    user_repo.update.side_effect = RuntimeError("write failed")

    with patch("app.services.password_reset_service.get_password_hash", return_value="hashed"):
        with pytest.raises(
            ValidationException,
            match="An error occurred while resetting your password",
        ):
            service.confirm_password_reset("tok_3", "NewPassword123!")

    db.rollback.assert_called()
    token_repo.update.assert_not_called()
