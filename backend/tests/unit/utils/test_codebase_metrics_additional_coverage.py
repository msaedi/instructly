"""Additional coverage tests for codebase metrics utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.codebase_metrics import collect_codebase_metrics


def test_collect_codebase_metrics_missing_script(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Metrics script not found"):
        collect_codebase_metrics(tmp_path)


def test_collect_codebase_metrics_missing_analyzer(tmp_path: Path, monkeypatch) -> None:
    script_path = tmp_path / "backend" / "scripts" / "codebase_metrics.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("# stub")

    monkeypatch.setattr("app.utils.codebase_metrics.runpy.run_path", lambda _path: {})

    with pytest.raises(RuntimeError, match="CodebaseAnalyzer"):
        collect_codebase_metrics(tmp_path)


def test_collect_codebase_metrics_success(tmp_path: Path, monkeypatch) -> None:
    script_path = tmp_path / "backend" / "scripts" / "codebase_metrics.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("# stub")

    class DummyAnalyzer:
        def __init__(self, repo_root: str) -> None:
            self.repo_root = repo_root

        def analyze_backend(self):
            return {"total_lines": 10, "total_files": 2}

        def analyze_frontend(self):
            return {"total_lines": 5, "total_files": 1}

        def get_git_stats(self):
            return {"commits": 1}

    monkeypatch.setattr(
        "app.utils.codebase_metrics.runpy.run_path",
        lambda _path: {"CodebaseAnalyzer": DummyAnalyzer},
    )

    result = collect_codebase_metrics(tmp_path)

    assert result["backend"]["total_lines"] == 10
    assert result["frontend"]["total_files"] == 1
    assert result["summary"]["total_lines"] == 15
