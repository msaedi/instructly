"""Persistent Celery task execution history model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ulid_helper import generate_ulid
from app.database import Base


class TaskExecutionStatus(str, Enum):
    """Persisted Celery task lifecycle states."""

    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"


class TaskExecution(Base):
    """Persistent task execution record used by admin APIs and MCP tools."""

    __tablename__ = "task_executions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    celery_task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    queue: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TaskExecutionStatus.STARTED.value,
        server_default=TaskExecutionStatus.STARTED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retries: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worker: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_task_executions_task_name_started", task_name, started_at.desc()),
        Index("ix_task_executions_status_started", status, started_at.desc()),
        Index("ix_task_executions_started_at", started_at.desc()),
        Index("ix_task_executions_celery_task_id", celery_task_id, unique=True),
    )
