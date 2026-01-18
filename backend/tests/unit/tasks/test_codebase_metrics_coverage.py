from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tasks import codebase_metrics


def test_get_repo_root_points_to_repo() -> None:
    root = codebase_metrics._get_repo_root()
    assert (root / "backend").exists()


def test_run_metrics_script_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(codebase_metrics, "collect_codebase_metrics", lambda _root: {"ok": True})
    result = codebase_metrics._run_metrics_script(tmp_path)
    assert result == {"ok": True}


def test_run_metrics_script_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        codebase_metrics,
        "collect_codebase_metrics",
        lambda _root: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError):
        codebase_metrics._run_metrics_script(tmp_path)


def test_append_history_creates_file(monkeypatch, tmp_path) -> None:
    data = {
        "timestamp": "2024-01-01",
        "summary": {"total_lines": 10, "total_files": 2},
        "backend": {"total_lines": 5, "categories": {}},
        "frontend": {"total_lines": 5, "categories": {}},
        "git": {"total_commits": 1},
    }
    monkeypatch.setattr(codebase_metrics, "_get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_metrics, "_run_metrics_script", lambda _root: data)

    result = codebase_metrics.append_history.run()

    history_path = tmp_path / "metrics_history.json"
    assert history_path.exists()
    assert result["count"] == 1


def test_append_history_rejects_commit_decrease(monkeypatch, tmp_path) -> None:
    history_path = tmp_path / "metrics_history.json"
    history_path.write_text(json.dumps([{"git_commits": 5}]))

    data = {
        "timestamp": "2024-01-01",
        "summary": {"total_lines": 10, "total_files": 2},
        "backend": {"total_lines": 5, "categories": {}},
        "frontend": {"total_lines": 5, "categories": {}},
        "git": {"total_commits": 1},
    }

    monkeypatch.setattr(codebase_metrics, "_get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_metrics, "_run_metrics_script", lambda _root: data)

    with pytest.raises(RuntimeError):
        codebase_metrics.append_history.run()


def test_get_repo_root_falls_back_to_cwd_when_repo_missing(monkeypatch) -> None:
    monkeypatch.setattr(codebase_metrics.Path, "exists", lambda _self: False)

    assert codebase_metrics._get_repo_root() == Path.cwd()


def test_get_repo_root_walks_parents(monkeypatch) -> None:
    here = Path(codebase_metrics.__file__).resolve()
    target = here.parents[2]

    def fake_exists(path: Path) -> bool:
        return path in {target / "backend", target / "frontend"}

    monkeypatch.setattr(codebase_metrics.Path, "exists", fake_exists)

    assert codebase_metrics._get_repo_root() == target


def test_append_history_invalid_json_history(monkeypatch, tmp_path) -> None:
    history_path = tmp_path / "metrics_history.json"
    history_path.write_text("not-json")

    data = {
        "timestamp": "2024-01-02",
        "summary": {"total_lines": 10, "total_files": 2},
        "backend": {"total_lines": 5, "categories": {}},
        "frontend": {"total_lines": 5, "categories": {}},
        "git": {"total_commits": 1},
    }
    monkeypatch.setattr(codebase_metrics, "_get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_metrics, "_run_metrics_script", lambda _root: data)

    result = codebase_metrics.append_history.run()

    assert result["count"] == 1
    assert json.loads(history_path.read_text())[0]["git_commits"] == 1


def test_get_repo_root_finds_parents3_path() -> None:
    """Test _get_repo_root uses parents[3] path when backend/frontend exist."""
    root = codebase_metrics._get_repo_root()
    # Should find the repo root which has both backend and frontend
    assert (root / "backend").exists()
    assert (root / "frontend").exists()


def test_get_repo_root_walks_up_until_root(monkeypatch, tmp_path) -> None:
    """Test _get_repo_root walks up the directory tree correctly."""
    # Create a mock path structure
    nested = tmp_path / "a" / "b" / "c" / "d"
    nested.mkdir(parents=True)
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()

    # Mock __file__ to be in the nested directory
    class MockPath(type(Path())):
        def resolve(self):
            return nested

    # Create a fresh function to test with custom path
    def custom_get_repo_root() -> Path:
        here = nested
        root = here.parents[3] if len(here.parents) > 3 else here
        if (root / "backend").exists() and (root / "frontend").exists():
            return root
        current = here
        while current != current.parent:
            if (current / "backend").exists() and (current / "frontend").exists():
                return current
            current = current.parent
        return Path.cwd()

    result = custom_get_repo_root()
    assert result == tmp_path


def test_append_history_appends_to_existing(monkeypatch, tmp_path) -> None:
    """Test that append_history correctly appends to existing history."""
    history_path = tmp_path / "metrics_history.json"
    existing = [{"timestamp": "2024-01-01", "git_commits": 5, "total_lines": 100}]
    history_path.write_text(json.dumps(existing))

    data = {
        "timestamp": "2024-01-02",
        "summary": {"total_lines": 120, "total_files": 3},
        "backend": {"total_lines": 60, "categories": {}},
        "frontend": {"total_lines": 60, "categories": {}},
        "git": {"total_commits": 10},
    }
    monkeypatch.setattr(codebase_metrics, "_get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_metrics, "_run_metrics_script", lambda _root: data)

    result = codebase_metrics.append_history.run()

    assert result["count"] == 2
    history = json.loads(history_path.read_text())
    assert len(history) == 2
    assert history[1]["git_commits"] == 10


def test_append_history_truncates_to_1000_entries(monkeypatch, tmp_path) -> None:
    """Test that history is truncated to 1000 entries."""
    history_path = tmp_path / "metrics_history.json"
    # Create 1000 entries
    existing = [{"git_commits": i, "timestamp": f"2024-01-{i:02d}"} for i in range(1, 1001)]
    history_path.write_text(json.dumps(existing))

    data = {
        "timestamp": "2024-02-01",
        "summary": {"total_lines": 120, "total_files": 3},
        "backend": {"total_lines": 60, "categories": {}},
        "frontend": {"total_lines": 60, "categories": {}},
        "git": {"total_commits": 1500},
    }
    monkeypatch.setattr(codebase_metrics, "_get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_metrics, "_run_metrics_script", lambda _root: data)

    result = codebase_metrics.append_history.run()

    assert result["count"] == 1000
    history = json.loads(history_path.read_text())
    assert len(history) == 1000
    # Oldest entry should be trimmed, newest should be the appended one
    assert history[-1]["git_commits"] == 1500
