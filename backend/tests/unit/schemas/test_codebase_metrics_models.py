from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.schemas.codebase_metrics_models import CodebaseHistoryEntry


def _payload(timestamp: str) -> dict:
    return {
        "timestamp": timestamp,
        "total_lines": 120,
        "total_files": 12,
        "backend_lines": 70,
        "frontend_lines": 50,
        "git_commits": 44,
        "categories": {"backend": {}, "frontend": {}},
        "backend_files": 7,
        "frontend_files": 5,
        "unique_contributors": 3,
        "first_commit_date": "2024-01-01",
        "last_commit_date": "2026-04-06",
        "branch": "main",
    }


def test_codebase_history_entry_accepts_utc_timestamps() -> None:
    entry = CodebaseHistoryEntry.model_validate(_payload("2026-04-06T15:00:00Z"))

    assert entry.timestamp.utcoffset() is not None


def test_codebase_history_entry_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone info"):
        CodebaseHistoryEntry.model_validate(_payload("2026-04-06T15:00:00"))


def test_codebase_history_entry_rejects_non_utc_timestamps() -> None:
    with pytest.raises(ValidationError, match="Timestamp must be UTC"):
        CodebaseHistoryEntry.model_validate(_payload("2026-04-06T10:00:00-05:00"))
