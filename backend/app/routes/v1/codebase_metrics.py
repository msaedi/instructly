"""Read-only codebase metrics routes backed by the committed history file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.enums import PermissionName
from ...dependencies.permissions import require_permission
from ...models.user import User
from ...schemas.codebase_metrics_models import CodebaseHistoryEntry

router = APIRouter(
    tags=["analytics"],
    responses={404: {"description": "Not found"}},
)


def _get_project_root() -> Path:
    """Resolve repository root (directory containing backend and frontend)."""
    here = Path(__file__).resolve()
    repo_root = here.parents[4]
    if not (repo_root / "backend").exists() or not (repo_root / "frontend").exists():
        current = here
        while current != current.parent:
            if (current / "backend").exists() and (current / "frontend").exists():
                return current
            current = current.parent
    return repo_root


def _read_metrics_history(repo_root: Path) -> List[dict[str, Any]]:
    """Read the committed metrics history file from the repository root."""
    history_file = repo_root / "metrics_history.json"
    if not history_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "metrics_history.json was not found in the repository root. "
                "Generate it locally with `python backend/scripts/codebase_metrics.py > "
                "metrics_history.json`, or commit from this checkout so the "
                "pre-commit hook can regenerate it automatically."
            ),
        )

    try:
        with history_file.open("r", encoding="utf-8") as handle:
            history = json.load(handle)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse metrics_history.json: {exc}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read metrics_history.json: {exc}",
        )

    if not isinstance(history, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="metrics_history.json must contain a JSON array.",
        )

    return history


@router.get("/metrics", response_model=List[CodebaseHistoryEntry])
async def get_codebase_metrics(
    current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
) -> List[CodebaseHistoryEntry]:
    """Return the committed codebase metrics history as raw JSON."""
    repo_root = _get_project_root()
    return [
        CodebaseHistoryEntry.model_validate(entry) for entry in _read_metrics_history(repo_root)
    ]
