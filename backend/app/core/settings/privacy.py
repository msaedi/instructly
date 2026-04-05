from __future__ import annotations

from pydantic import Field


class PrivacySettingsMixin:
    search_event_retention_days: int = 365
    booking_pii_retention_days: int = 2555
    alert_retention_days: int = 365
    privacy_data_export_enabled: bool = True
    privacy_data_deletion_enabled: bool = True
    availability_retention_enabled: bool = Field(
        default=False,
        alias="AVAILABILITY_RETENTION_ENABLED",
        description="Enable scheduled purge of stale availability_days rows",
    )
    availability_retention_days: int = Field(
        default=180,
        alias="AVAILABILITY_RETENTION_DAYS",
        ge=0,
        description="TTL in days before bitmap availability entries become purge candidates",
    )
    availability_retention_keep_recent_days: int = Field(
        default=30,
        alias="AVAILABILITY_RETENTION_KEEP_RECENT_DAYS",
        ge=0,
        description="Minimum recent history (days) to always keep even if TTL exceeded",
    )
    availability_retention_dry_run: bool = Field(
        default=False,
        alias="AVAILABILITY_RETENTION_DRY_RUN",
        description="When true, retention logs counts without deleting availability_days rows",
    )
    task_execution_retention_days: int = Field(
        default=90,
        alias="TASK_EXECUTION_RETENTION_DAYS",
        ge=1,
        description="TTL in days before historical task_executions rows are purged",
    )
