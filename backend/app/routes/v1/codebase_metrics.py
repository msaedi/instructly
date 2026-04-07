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
    """Find repo root by walking up looking for .git directory."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Could not find repo root (.git not found)")


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
    _current_user: User = Depends(require_permission(PermissionName.VIEW_SYSTEM_ANALYTICS)),
) -> List[CodebaseHistoryEntry]:
    """Return the committed codebase metrics history as raw JSON."""
    repo_root = _get_project_root()
    return [
        CodebaseHistoryEntry.model_validate(entry) for entry in _read_metrics_history(repo_root)
    ]
