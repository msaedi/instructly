"""
Base response schemas for standardized API responses.

These schemas ensure consistent response formats across all API endpoints,
eliminating the need for defensive coding in the frontend.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictModel

T = TypeVar("T")


class EmptyResponse(StrictModel):
    """Empty response body placeholder (use with 204 No Content)."""

    model_config = ConfigDict(json_schema_extra={"example": {}})


class PaginatedResponse(StrictModel, Generic[T]):
    """
    Standard paginated response for all list endpoints.

    This replaces inconsistent patterns like returning raw arrays or
    resource-specific field names (bookings, instructors, etc.).
    """

    items: List[T] = Field(description="List of items")
    total: int = Field(description="Total number of items")
    page: int = Field(default=1, description="Current page number", ge=1)
    per_page: int = Field(default=20, description="Items per page", ge=1, le=100)
    has_next: bool = Field(description="Whether there's a next page")
    has_prev: bool = Field(description="Whether there's a previous page")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": ["..."],
                "total": 100,
                "page": 1,
                "per_page": 20,
                "has_next": True,
                "has_prev": False,
            }
        }
    )


class SuccessResponse(StrictModel):
    """Standard success response for operations."""

    success: bool = Field(default=True, description="Operation success status")
    message: str = Field(description="Human-readable success message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Optional additional data")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"updated_fields": ["name", "email"]},
            }
        }
    )


class BaseDeleteResponse(StrictModel):
    """Standard response for delete operations."""

    success: bool = Field(default=True, description="Deletion success status")
    message: str = Field(description="Human-readable deletion message")
    deleted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Deletion timestamp"
    )

    model_config = ConfigDict(
        title="BaseDeleteResponse",
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Resource deleted successfully",
                "deleted_at": "2025-01-20T10:30:00Z",
            }
        },
    )


# Backward-compatible alias for existing imports.
DeleteResponse = BaseDeleteResponse


class ErrorDetail(BaseModel):
    """Standard error detail structure."""

    code: str = Field(description="Error code for programmatic handling")
    message: str = Field(description="Human-readable error message")
    field: Optional[str] = Field(default=None, description="Field that caused the error")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid date format",
                "field": "booking_date",
            }
        }
    )


class ErrorResponse(StrictModel):
    """
    Standard error response structure.

    This replaces inconsistent error formats like:
    - {"detail": "error message"}
    - {"message": "error message"}
    - {"error": "error message"}
    """

    error: ErrorDetail = Field(description="Error details")
    request_id: Optional[str] = Field(default=None, description="Request ID for tracking")
    trace_id: Optional[str] = Field(default=None, description="Trace ID for distributed tracing")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Error timestamp"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "Instructor not found",
                    "field": None,
                },
                "request_id": "req_123abc",
                "trace_id": "0af7651916cd43dd8448eb211c80319c",
                "timestamp": "2025-01-20T10:30:00Z",
            }
        }
    )


class BatchOperationResult(BaseModel):
    """Standard response for batch operations."""

    total: int = Field(description="Total number of items processed")
    successful: int = Field(description="Number of successful operations")
    failed: int = Field(description="Number of failed operations")
    errors: List[ErrorDetail] = Field(
        default_factory=list, description="List of errors for failed items"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 10,
                "successful": 8,
                "failed": 2,
                "errors": [
                    {"code": "VALIDATION_ERROR", "message": "Invalid date", "field": "date"}
                ],
            }
        }
    )


class HealthCheckResponse(StrictModel):
    """Standard health check response."""

    status: str = Field(
        description="Service health status", pattern="^(healthy|degraded|unhealthy)$"
    )
    service: str = Field(default="iNSTAiNSTRU API", description="Service name")
    version: str = Field(description="API version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Check timestamp"
    )
    checks: Dict[str, bool] = Field(description="Individual component health checks")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "status": "healthy",
                "service": "iNSTAiNSTRU API",
                "version": "1.0.0",
                "timestamp": "2025-01-20T10:30:00Z",
                "checks": {"database": True, "redis": True, "services": True},
            }
        },
    )


class MetricsResponse(StrictModel):
    """Standard metrics response."""

    metrics: Dict[str, float] = Field(description="Metric values")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Metrics timestamp"
    )
    period: str = Field(description="Time period for metrics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "metrics": {
                    "requests_per_second": 123.45,
                    "average_response_time_ms": 234.56,
                    "error_rate": 0.01,
                },
                "timestamp": "2025-01-20T10:30:00Z",
                "period": "last_5_minutes",
            }
        }
    )


def create_paginated_response(
    items: List[T], total: int, page: int = 1, per_page: int = 20
) -> PaginatedResponse[T]:
    """
    Helper function to create a paginated response.

    Args:
        items: List of items for current page
        total: Total count of all items
        page: Current page number
        per_page: Items per page

    Returns:
        PaginatedResponse with calculated pagination metadata
    """
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_next=page * per_page < total,
        has_prev=page > 1,
    )
