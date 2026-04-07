from __future__ import annotations

import json
from pathlib import Path

import pytest
import scripts.codebase_metrics as codebase_metrics_script


def _current_entry(timestamp: str = "2026-04-06T15:00:00+00:00") -> dict:
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
        "branch": "fix/codebase-metrics-prepush",
    }


def test_build_history_backfills_legacy_entries_and_appends_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    legacy_history = [
        {
            "timestamp": "2026-04-05T15:00:00",
            "total_lines": 100,
            "total_files": 10,
            "backend_lines": 60,
            "frontend_lines": 40,
            "git_commits": 40,
        }
    ]
    (tmp_path / "metrics_history.json").write_text(json.dumps(legacy_history), encoding="utf-8")
    monkeypatch.setattr(codebase_metrics_script.CodebaseAnalyzer, "build_entry", lambda self: _current_entry())

    history = codebase_metrics_script.build_history(tmp_path)

    assert len(history) == 2
    assert history[0]["backend_files"] is None
    assert history[0]["frontend_files"] is None
    assert history[0]["unique_contributors"] is None
    assert history[0]["first_commit_date"] is None
    assert history[0]["last_commit_date"] is None
    assert history[0]["branch"] is None
    assert history[0]["categories"] is None
    assert history[-1]["branch"] == "fix/codebase-metrics-prepush"


def test_build_history_is_idempotent_for_matching_latest_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    current_entry = _current_entry(timestamp="2026-04-06T15:00:00+00:00")
    prior_entry = dict(current_entry)
    prior_entry["timestamp"] = "2026-04-05T15:00:00+00:00"
    (tmp_path / "metrics_history.json").write_text(json.dumps([prior_entry]), encoding="utf-8")
    monkeypatch.setattr(codebase_metrics_script.CodebaseAnalyzer, "build_entry", lambda self: current_entry)

    history = codebase_metrics_script.build_history(tmp_path)

    assert history == [prior_entry]


def test_build_history_reads_committed_history_when_worktree_file_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    legacy_history = [
        {
            "timestamp": "2026-04-05T15:00:00",
            "total_lines": 100,
            "total_files": 10,
            "backend_lines": 60,
            "frontend_lines": 40,
            "git_commits": 40,
        }
    ]
    (tmp_path / "metrics_history.json").write_text("", encoding="utf-8")

    class CompletedProcess:
        returncode = 0
        stdout = json.dumps(legacy_history)

    monkeypatch.setattr(
        codebase_metrics_script.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(),
    )
    monkeypatch.setattr(codebase_metrics_script.CodebaseAnalyzer, "build_entry", lambda self: _current_entry())

    history = codebase_metrics_script.build_history(tmp_path)

    assert len(history) == 2
    assert history[0]["git_commits"] == 40
    assert history[-1]["git_commits"] == 44
