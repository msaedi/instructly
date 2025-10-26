from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.tasks import badge_tasks


def test_finalize_pending_badges_task(monkeypatch):
    mock_db = MagicMock()
    mock_session_local = MagicMock(return_value=mock_db)
    monkeypatch.setattr(badge_tasks, "SessionLocal", mock_session_local)

    mock_service = MagicMock()
    mock_service.finalize_pending_badges.return_value = {"confirmed": 2, "revoked": 1}
    monkeypatch.setattr(badge_tasks, "BadgeAwardService", MagicMock(return_value=mock_service))

    result = badge_tasks.finalize_pending_badges_task()

    assert result == {"confirmed": 2, "revoked": 1}
    mock_service.finalize_pending_badges.assert_called_once()
    args, _ = mock_service.finalize_pending_badges.call_args
    assert isinstance(args[0], datetime)
    assert args[0].tzinfo == timezone.utc
    mock_db.close.assert_called_once()
