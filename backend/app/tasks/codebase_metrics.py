"""
Celery tasks for codebase metrics history persistence.

This appends a daily snapshot to metrics_history.json by running the
existing backend/scripts/codebase_metrics.py with --json.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Dict, List, TypeVar, cast

from app.tasks.celery_app import BaseTask, celery_app

TaskCallable = TypeVar("TaskCallable", bound=Callable[..., Any])


def _get_repo_root() -> Path:
    here = Path(__file__).resolve()
    # backend/app/tasks/codebase_metrics.py -> repo root is parents[3]
    root = here.parents[3]
    if (root / "backend").exists() and (root / "frontend").exists():
        return root
    current = here
    while current != current.parent:
        if (current / "backend").exists() and (current / "frontend").exists():
            return current
        current = current.parent
    return Path.cwd()


def _run_metrics_script(repo_root: Path) -> Dict[str, Any]:
    script_path = repo_root / "backend" / "scripts" / "codebase_metrics.py"
    result = subprocess.run(
        ["python3", str(script_path), "--json", "--path", str(repo_root)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "metrics script failed")
    return cast(Dict[str, Any], json.loads(result.stdout))


def typed_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskCallable], TaskCallable]:
    return cast(Callable[[TaskCallable], TaskCallable], celery_app.task(*task_args, **task_kwargs))


@typed_task(
    base=BaseTask,
    name="app.tasks.codebase_metrics.append_history",
    bind=True,
    max_retries=2,
    retry_backoff=True,
)
def append_history(self: BaseTask) -> Dict[str, Any]:
    """Append current snapshot to metrics_history.json.

    Returns: summary with count after append.
    """
    repo_root = _get_repo_root()
    history_file = repo_root / "metrics_history.json"

    # Compute current snapshot
    data = _run_metrics_script(repo_root)

    entry = {
        "timestamp": data.get("timestamp"),
        "total_lines": data.get("summary", {}).get("total_lines", 0),
        "total_files": data.get("summary", {}).get("total_files", 0),
        "backend_lines": data.get("backend", {}).get("total_lines", 0),
        "frontend_lines": data.get("frontend", {}).get("total_lines", 0),
        "git_commits": data.get("git", {}).get("total_commits", 0),
        "categories": {
            "backend": data.get("backend", {}).get("categories", {}),
            "frontend": data.get("frontend", {}).get("categories", {}),
        },
    }

    # Load existing history
    history: List[Dict[str, Any]] = []
    if history_file.exists():
        try:
            history = cast(List[Dict[str, Any]], json.loads(history_file.read_text()))
        except Exception:
            history = []

    if history:
        prev_git = history[-1].get("git_commits", 0)
        if entry["git_commits"] < prev_git:
            raise RuntimeError(
                "Refusing to append codebase metrics: git commit total would decrease."
            )

    history.append(entry)
    history = history[-1000:]

    history_file.write_text(json.dumps(history, indent=2))

    return {"status": "ok", "count": len(history)}
