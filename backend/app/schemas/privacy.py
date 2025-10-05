# backend/app/schemas/privacy.py
"""
Pydantic schemas for privacy and GDPR compliance.
"""

from typing import Any, Dict

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel


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
    statistics: Dict[str, Any] = Field(description="Privacy and retention statistics")


class RetentionPolicyResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """
    Response schema for applying retention policies.
    """

    status: str = Field(description="Status of the retention policy application")
    message: str = Field(description="Human-readable message")
    stats: Dict[str, Any] = Field(description="Statistics of retention policy application")
