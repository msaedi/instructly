from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tasks import codebase_metrics


def test_get_repo_root_points_to_repo() -> None:
    root = codebase_metrics._get_repo_root()
    assert (root / "backend").exists()


def test_run_metrics_script_success(monkeypatch, tmp_path) -> None:
    class DummyResult:
        returncode = 0
        stdout = json.dumps({"ok": True})
        stderr = ""

    monkeypatch.setattr(codebase_metrics.subprocess, "run", lambda *_a, **_k: DummyResult())
    result = codebase_metrics._run_metrics_script(tmp_path)
    assert result == {"ok": True}


def test_run_metrics_script_failure(monkeypatch, tmp_path) -> None:
    class DummyResult:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(codebase_metrics.subprocess, "run", lambda *_a, **_k: DummyResult())
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
