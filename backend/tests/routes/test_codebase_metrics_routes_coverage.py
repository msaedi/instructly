from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

import app.routes.v1.codebase_metrics as codebase_routes


def _sample_history() -> list[dict]:
    return [
        {
            "timestamp": "2025-01-01T00:00:00",
            "total_lines": 18,
            "total_files": 2,
            "backend_lines": 10,
            "frontend_lines": 8,
            "git_commits": 5,
            "categories": {"backend": {}, "frontend": {}},
            "backend_files": 1,
            "frontend_files": 1,
            "unique_contributors": 2,
            "first_commit_date": "2020-01-01",
            "last_commit_date": "2025-01-01",
            "branch": "main",
        }
    ]


def test_get_project_root_finds_git_root(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "backend").mkdir(parents=True)
    (repo_root / "frontend").mkdir(parents=True)

    nested_file = repo_root / "apps" / "backend" / "app" / "routes" / "v1" / "codebase_metrics.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("# stub")

    monkeypatch.setattr(codebase_routes, "Path", lambda *_args, **_kwargs: nested_file)
    assert codebase_routes._get_project_root() == repo_root


def test_read_metrics_history_missing(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        codebase_routes._read_metrics_history(tmp_path)

    assert exc.value.status_code == 404
    assert "pre-commit hook" in exc.value.detail


def test_read_metrics_history_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "metrics_history.json").write_text("{", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        codebase_routes._read_metrics_history(tmp_path)

    assert exc.value.status_code == 500
    assert "Failed to parse metrics_history.json" in exc.value.detail


def test_read_metrics_history_rejects_non_array(tmp_path: Path) -> None:
    (tmp_path / "metrics_history.json").write_text(json.dumps({"oops": True}), encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        codebase_routes._read_metrics_history(tmp_path)

    assert exc.value.status_code == 500
    assert "JSON array" in exc.value.detail


def test_get_codebase_metrics_endpoint(client, auth_headers_admin, monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "metrics_history.json").write_text(json.dumps(_sample_history()), encoding="utf-8")
    monkeypatch.setattr(codebase_routes, "_get_project_root", lambda: tmp_path)

    response = client.get("/api/v1/analytics/codebase/metrics", headers=auth_headers_admin)
    assert response.status_code == 200
    assert response.json()[0]["total_lines"] == 18
    assert response.json()[0]["branch"] == "main"


def test_get_codebase_metrics_endpoint_missing_file(
    client, auth_headers_admin, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(codebase_routes, "_get_project_root", lambda: tmp_path)

    response = client.get("/api/v1/analytics/codebase/metrics", headers=auth_headers_admin)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_codebase_metrics_validates_history_entries(
    monkeypatch, tmp_path: Path
) -> None:
    history = _sample_history()
    history[0]["unexpected"] = True
    (tmp_path / "metrics_history.json").write_text(json.dumps(history), encoding="utf-8")
    monkeypatch.setattr(codebase_routes, "_get_project_root", lambda: tmp_path)

    with pytest.raises(ValidationError) as exc:
        await codebase_routes.get_codebase_metrics()

    assert "unexpected" in str(exc.value)
