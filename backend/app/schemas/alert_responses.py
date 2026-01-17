"""
Response models for alert monitoring endpoints.

These models ensure consistent API responses for alert-related endpoints
and provide proper documentation through FastAPI's automatic docs.
"""

from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel

# ============================================================================
# Alert Details - Discriminated Union by alert_type
# ============================================================================


class ExtremelySlowQueryDetails(StrictModel):
    """Details for extremely slow database queries."""

    alert_type: Literal["extremely_slow_query"] = Field(
        default="extremely_slow_query", description="Alert type discriminator"
    )
    duration_ms: float = Field(description="Query duration in milliseconds")
    query_preview: str = Field(description="First 200 chars of the query")
    full_query: Optional[str] = Field(
        default=None, description="Full query text (only for queries > 2000ms)"
    )


class ExtremelySlowRequestDetails(StrictModel):
    """Details for extremely slow HTTP requests."""

    alert_type: Literal["extremely_slow_request"] = Field(
        default="extremely_slow_request", description="Alert type discriminator"
    )
    duration_ms: float = Field(description="Request duration in milliseconds")
    method: str = Field(description="HTTP method (GET, POST, etc.)")
    path: str = Field(description="Request path")
    status_code: int = Field(description="HTTP response status code")
    client: str = Field(description="Client IP address")


class HighDbPoolUsageDetails(StrictModel):
    """Details for high database connection pool usage."""

    alert_type: Literal["high_db_pool_usage"] = Field(
        default="high_db_pool_usage", description="Alert type discriminator"
    )
    usage_percent: Optional[float] = Field(default=None, description="Pool usage percentage")
    checked_out: Optional[int] = Field(
        default=None, description="Number of checked out connections"
    )
    total_possible: Optional[int] = Field(default=None, description="Total possible connections")


class HighMemoryUsageDetails(StrictModel):
    """Details for high memory usage alerts."""

    alert_type: Literal["high_memory_usage"] = Field(
        default="high_memory_usage", description="Alert type discriminator"
    )
    memory_mb: Optional[float] = Field(default=None, description="Memory usage in MB")
    percent: Optional[float] = Field(default=None, description="Memory usage percentage")


class LowCacheHitRateDetails(StrictModel):
    """Details for low cache hit rate alerts."""

    alert_type: Literal["low_cache_hit_rate"] = Field(
        default="low_cache_hit_rate", description="Alert type discriminator"
    )
    hit_rate: Optional[float] = Field(default=None, description="Current cache hit rate")
    target: Optional[float] = Field(default=None, description="Target cache hit rate")


# Discriminated union of all alert details types
AlertDetailsUnion = Annotated[
    Union[
        ExtremelySlowQueryDetails,
        ExtremelySlowRequestDetails,
        HighDbPoolUsageDetails,
        HighMemoryUsageDetails,
        LowCacheHitRateDetails,
    ],
    Field(discriminator="alert_type"),
]


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
    details: Optional[AlertDetailsUnion] = Field(
        default=None, description="Type-specific alert details"
    )


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
