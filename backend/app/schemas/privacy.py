# backend/app/schemas/privacy.py
"""
Pydantic schemas for privacy and GDPR compliance.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field


class UserDataDeletionRequest(BaseModel):
    """
    Request schema for user data deletion.
    """

    delete_account: bool = Field(
        default=False, description="Whether to delete the entire account or just anonymize data"
    )


class UserDataDeletionResponse(BaseModel):
    """
    Response schema for user data deletion.
    """

    status: str = Field(description="Status of the deletion request")
    message: str = Field(description="Human-readable message")
    deletion_stats: Dict[str, int] = Field(description="Statistics of deleted records")
    account_deleted: bool = Field(description="Whether the account was deleted")


class DataExportResponse(BaseModel):
    """
    Response schema for data export requests.
    """

    status: str = Field(description="Status of the export request")
    message: str = Field(description="Human-readable message")
    data: Dict[str, Any] = Field(description="The exported user data")


class PrivacyStatisticsResponse(BaseModel):
    """
    Response schema for privacy statistics.
    """

    status: str = Field(description="Status of the request")
    statistics: Dict[str, Any] = Field(description="Privacy and retention statistics")
