from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

import app.routes.v1.codebase_metrics as codebase_routes


def _sample_metrics() -> dict:
    return {
        "timestamp": "2025-01-01T00:00:00Z",
        "backend": {
            "total_files": 1,
            "total_lines": 10,
            "total_lines_with_blanks": 12,
            "categories": {},
            "largest_files": [],
        },
        "frontend": {
            "total_files": 1,
            "total_lines": 8,
            "total_lines_with_blanks": 9,
            "categories": {},
            "largest_files": [],
        },
        "git": {
            "total_commits": 5,
            "unique_contributors": 2,
            "first_commit": "2020-01-01",
            "last_commit": "2025-01-01",
            "current_branch": "main",
        },
        "summary": {"total_lines": 18, "total_files": 2},
    }


def test_normalize_timestamp() -> None:
    assert codebase_routes._normalize_timestamp(None) is None
    assert codebase_routes._normalize_timestamp("2025-01-01T00:00:00") == "2025-01-01T00:00:00Z"
    assert codebase_routes._normalize_timestamp("2025-01-01T00:00:00Z") == "2025-01-01T00:00:00Z"


def test_run_codebase_metrics_script_missing(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        codebase_routes._run_codebase_metrics_script(tmp_path)

    assert exc.value.status_code == 500


def test_run_codebase_metrics_script_failure(tmp_path: Path, monkeypatch) -> None:
    backend_dir = tmp_path / "backend" / "scripts"
    backend_dir.mkdir(parents=True)
    script = backend_dir / "codebase_metrics.py"
    script.write_text("print('hi')")

    monkeypatch.setattr(
        codebase_routes.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )

    with pytest.raises(HTTPException) as exc:
        codebase_routes._run_codebase_metrics_script(tmp_path)

    assert "Metrics process failed" in exc.value.detail


def test_run_codebase_metrics_script_bad_json(tmp_path: Path, monkeypatch) -> None:
    backend_dir = tmp_path / "backend" / "scripts"
    backend_dir.mkdir(parents=True)
    script = backend_dir / "codebase_metrics.py"
    script.write_text("print('hi')")

    monkeypatch.setattr(
        codebase_routes.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="bad", stderr=""),
    )

    with pytest.raises(HTTPException) as exc:
        codebase_routes._run_codebase_metrics_script(tmp_path)

    assert "Invalid JSON" in exc.value.detail


def test_get_codebase_metrics_endpoint(client, auth_headers_admin, monkeypatch) -> None:
    monkeypatch.setattr(codebase_routes, "_run_codebase_metrics_script", lambda _root: _sample_metrics())

    response = client.get("/api/v1/analytics/codebase/metrics", headers=auth_headers_admin)
    assert response.status_code == 200
    assert response.json()["summary"]["total_lines"] == 18


def test_get_codebase_metrics_history_seeds_when_missing(
    client, auth_headers_admin, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(codebase_routes, "_get_project_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_routes, "_run_codebase_metrics_script", lambda _root: _sample_metrics())

    response = client.get("/api/v1/analytics/codebase/history", headers=auth_headers_admin)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["current"]["summary"]["total_files"] == 2


def test_get_codebase_metrics_history_reads_and_normalizes(
    client, auth_headers_admin, monkeypatch, tmp_path: Path
) -> None:
    history_file = tmp_path / "metrics_history.json"
    history_file.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2025-01-02T00:00:00",
                    "total_lines": 1,
                    "total_files": 1,
                    "backend_lines": 1,
                    "frontend_lines": 0,
                    "git_commits": 1,
                }
            ]
        )
    )
    monkeypatch.setattr(codebase_routes, "_get_project_root", lambda: tmp_path)

    response = client.get("/api/v1/analytics/codebase/history", headers=auth_headers_admin)
    assert response.status_code == 200
    assert response.json()["items"][0]["timestamp"].endswith("Z")


def test_append_codebase_metrics_history(
    client, auth_headers_admin, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(codebase_routes, "_get_project_root", lambda: tmp_path)
    monkeypatch.setattr(codebase_routes, "_run_codebase_metrics_script", lambda _root: _sample_metrics())

    response = client.post("/api/v1/analytics/codebase/history/append", headers=auth_headers_admin)
    assert response.status_code == 200

    history_file = tmp_path / "metrics_history.json"
    assert history_file.exists()


def test_schema_reference_endpoints(client, auth_headers_admin) -> None:
    for path in [
        "/api/v1/analytics/codebase/_schemas/codebase/history-entry",
        "/api/v1/analytics/codebase/_schemas/codebase/category-stats",
        "/api/v1/analytics/codebase/_schemas/codebase/section",
        "/api/v1/analytics/codebase/_schemas/codebase/file-info",
        "/api/v1/analytics/codebase/_schemas/codebase/git-stats",
        "/api/v1/analytics/codebase/_schemas/codebase/summary",
    ]:
        response = client.get(path, headers=auth_headers_admin)
        assert response.status_code == 200
