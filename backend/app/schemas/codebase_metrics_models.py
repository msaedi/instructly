"""Pydantic models for committed codebase metrics history entries."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from pydantic import AwareDatetime, Field, field_validator

from ._strict_base import StrictModel


class CodebaseCategoryStats(StrictModel):
    files: int = Field(..., ge=0)
    lines: int = Field(..., ge=0)


class CodebaseHistoryEntry(StrictModel):
    timestamp: AwareDatetime
    total_lines: int = Field(..., ge=0)
    total_files: int = Field(..., ge=0)
    backend_lines: int = Field(..., ge=0)
    frontend_lines: int = Field(..., ge=0)
    git_commits: int = Field(..., ge=0)
    categories: Optional[Dict[str, Dict[str, CodebaseCategoryStats]]] = None
    backend_files: Optional[int] = Field(default=None, ge=0)
    frontend_files: Optional[int] = Field(default=None, ge=0)
    unique_contributors: Optional[int] = Field(default=None, ge=0)
    first_commit_date: Optional[str] = None
    last_commit_date: Optional[str] = None
    branch: Optional[str] = None

    @field_validator("timestamp", mode="after")
    @classmethod
    def _require_utc_timestamp(cls, value: datetime) -> datetime:
        """Codebase metrics timestamps must be timezone-aware UTC."""
        if value.utcoffset() != timedelta(0):
            raise ValueError("Timestamp must be UTC")
        return value
