"""Alias repository for enqueuing generic background jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .background_job_repository import BackgroundJobRepository


class JobRepository(BackgroundJobRepository):
    """Thin wrapper over BackgroundJobRepository for generic job queue usage."""

    def __init__(self, db: Session):
        super().__init__(db)

    def enqueue(
        self, *, type: str, payload: dict[str, Any] | str, available_at: datetime | None = None
    ) -> str:
        """Enqueue a job with a friendly signature for non-BGC workflows."""
        return super().enqueue(type=type, payload=payload, available_at=available_at)
