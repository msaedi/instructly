# backend/app/schemas/privacy.py
"""
Pydantic schemas for privacy and GDPR compliance.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel

# ============================================================================
# Typed models for privacy statistics
# ============================================================================


class PrivacyStatistics(BaseModel):
    """Privacy and retention statistics returned by get_privacy_statistics."""

    total_users: int = Field(description="Total number of users")
    active_users: int = Field(description="Number of active users")
    search_history_records: int = Field(description="Number of search history records")
    search_event_records: int = Field(description="Number of search event records")
    total_bookings: int = Field(description="Total number of bookings")
    search_events_eligible_for_deletion: Optional[int] = Field(
        default=None, description="Search events eligible for deletion based on retention policy"
    )


class RetentionStats(BaseModel):
    """Statistics from applying retention policies."""

    search_events_deleted: int = Field(default=0, description="Number of search events deleted")
    old_bookings_anonymized: int = Field(default=0, description="Number of old bookings anonymized")


class UserDataDeletionRequest(StrictRequestModel):
    """
    Request schema for user data deletion.
    """

    delete_account: bool = Field(
        default=False, description="Whether to delete the entire account or just anonymize data"
    )


class UserDataDeletionResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """
    Response schema for user data deletion.
    """

    status: str = Field(description="Status of the deletion request")
    message: str = Field(description="Human-readable message")
    deletion_stats: Dict[str, int] = Field(description="Statistics of deleted records")
    account_deleted: bool = Field(description="Whether the account was deleted")


class DataExportResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """
    Response schema for data export requests.
    """

    status: str = Field(description="Status of the export request")
    message: str = Field(description="Human-readable message")
    data: Dict[str, Any] = Field(description="The exported user data")


class PrivacyStatisticsResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """
    Response schema for privacy statistics.
    """

    status: str = Field(description="Status of the request")
    statistics: PrivacyStatistics = Field(description="Privacy and retention statistics")


class RetentionPolicyResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """
    Response schema for applying retention policies.
    """

    status: str = Field(description="Status of the retention policy application")
    message: str = Field(description="Human-readable message")
    stats: RetentionStats = Field(description="Statistics of retention policy application")
