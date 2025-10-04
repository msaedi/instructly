"""
Response models for alert monitoring endpoints.

These models ensure consistent API responses for alert-related endpoints
and provide proper documentation through FastAPI's automatic docs.
"""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel


class AlertDetail(StrictModel):
    """Individual alert details."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    id: str = Field(description="Alert ID")
    type: str = Field(description="Type of alert")
    severity: str = Field(description="Alert severity level")
    title: str = Field(description="Alert title")
    message: str = Field(description="Alert message")
    created_at: str = Field(description="When the alert was created (ISO format)")
    email_sent: bool = Field(description="Whether email notification was sent")
    github_issue: bool = Field(description="Whether GitHub issue was created")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional alert details")


class RecentAlertsResponse(StrictModel):
    """Response for recent alerts endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    total: int = Field(description="Total number of alerts in the time period")
    hours: int = Field(description="Number of hours included in the query")
    alerts: List[AlertDetail] = Field(description="List of alert details")


class DailyAlertCount(StrictModel):
    """Daily alert count for summary."""

    date: str = Field(description="Date in YYYY-MM-DD format")
    count: int = Field(description="Number of alerts on this date")


class AlertSummaryResponse(StrictModel):
    """Response for alert summary endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    days: int = Field(description="Number of days included in summary")
    by_type: Dict[str, int] = Field(description="Alert counts grouped by type")
    by_severity: Dict[str, int] = Field(description="Alert counts grouped by severity")
    by_day: List[DailyAlertCount] = Field(description="Daily alert counts")
    total: int = Field(description="Total number of alerts in the period")


class LiveAlertItem(StrictModel):
    """Simplified alert item for live view."""

    time: str = Field(description="Time in HH:MM:SS format")
    severity: str = Field(description="Alert severity (uppercase)")
    type: str = Field(description="Alert type")
    message: str = Field(description="Alert message (truncated if long)")


class LiveAlertsResponse(StrictModel):
    """Response for live alerts endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    minutes: int = Field(description="Number of minutes included")
    count: int = Field(description="Number of alerts in the time period")
    alerts: List[LiveAlertItem] = Field(description="List of recent alerts")
