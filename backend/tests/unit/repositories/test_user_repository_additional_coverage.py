from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.repositories.user_repository import UserRepository


def test_get_active_admin_users_returns_empty_on_query_error() -> None:
    failing_db = Mock()
    failing_db.query.side_effect = RuntimeError("boom")
    repo = UserRepository(failing_db)

    assert repo.get_active_admin_users() == []


def test_invalidate_all_tokens_ignores_metrics_failures_and_still_succeeds() -> None:
    db = Mock()
    repo = UserRepository(db)
    user = SimpleNamespace(tokens_valid_after=None)
    repo.get_by_id = Mock(return_value=user)

    with (
        patch(
            "app.monitoring.prometheus_metrics.prometheus_metrics.record_token_revocation",
            side_effect=RuntimeError("metrics down"),
        ),
        patch("app.core.auth_cache.invalidate_cached_user_by_id_sync", return_value=True),
    ):
        result = repo.invalidate_all_tokens("user-1", trigger="manual")

    assert result is True
    assert user.tokens_valid_after is not None
    db.commit.assert_called_once()


def test_invalidate_all_tokens_returns_false_when_cache_invalidation_raises() -> None:
    db = Mock()
    repo = UserRepository(db)
    user = SimpleNamespace(tokens_valid_after=None)
    repo.get_by_id = Mock(return_value=user)

    with patch(
        "app.core.auth_cache.invalidate_cached_user_by_id_sync",
        side_effect=RuntimeError("cache down"),
    ):
        result = repo.invalidate_all_tokens("user-1")

    assert result is False
    db.rollback.assert_called_once()


def test_lock_account_handles_missing_user_and_lookup_errors() -> None:
    repo = UserRepository(Mock())
    repo.get_by_id = Mock(return_value=None)

    assert repo.lock_account("missing-user", "manual review") is False

    repo.get_by_id.side_effect = RuntimeError("lookup failed")
    assert repo.lock_account("broken-user", "manual review") is False
