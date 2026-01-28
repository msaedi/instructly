"""MCP Admin endpoints for metric definitions (service token auth)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.mcp import MCPActor, MCPMeta, MCPMetricDefinition, MCPMetricResponse

router = APIRouter(tags=["MCP Admin - Metrics"])

METRIC_DEFINITIONS: dict[str, MCPMetricDefinition] = {
    "instructor.registered": MCPMetricDefinition(
        metric="instructor.registered",
        definition="User signed up with an instructor role.",
        requirements=["User has instructor role"],
        source_fields=["users.is_instructor"],
        related_metrics=["instructor.onboarding", "instructor.live"],
    ),
    "instructor.onboarding": MCPMetricDefinition(
        metric="instructor.onboarding",
        definition="Instructor has started onboarding but is not yet live.",
        requirements=[
            "Profile created",
            "Not live (is_live=false)",
        ],
        source_fields=[
            "instructor_profiles.onboarding_completed_at",
            "instructor_profiles.is_live",
            "instructor_profiles.skills_configured",
            "instructor_profiles.bgc_status",
        ],
        related_metrics=["instructor.registered", "instructor.live"],
    ),
    "instructor.live": MCPMetricDefinition(
        metric="instructor.live",
        definition="Instructor can accept bookings.",
        requirements=[
            "Profile completed (onboarding_completed_at is set)",
            "Background check passed (bgc_status='passed')",
            "At least one active service configured",
            "is_live=true",
        ],
        source_fields=[
            "instructor_profiles.is_live",
            "instructor_profiles.bgc_status",
            "instructor_profiles.onboarding_completed_at",
            "instructor_services.is_active",
        ],
        related_metrics=["instructor.onboarding", "instructor.paused"],
    ),
    "instructor.paused": MCPMetricDefinition(
        metric="instructor.paused",
        definition="Instructor was live but is currently paused.",
        requirements=["is_live=false", "onboarding_completed_at is set"],
        source_fields=[
            "instructor_profiles.is_live",
            "instructor_profiles.onboarding_completed_at",
        ],
        related_metrics=["instructor.live"],
    ),
    "founding.cap": MCPMetricDefinition(
        metric="founding.cap",
        definition="Maximum number of founding instructors allowed.",
        requirements=["Configured in pricing config"],
        source_fields=["pricing_config.founding_instructor_cap"],
        related_metrics=["founding.used"],
    ),
    "founding.used": MCPMetricDefinition(
        metric="founding.used",
        definition="Current count of founding instructors.",
        requirements=["Instructor profile flagged as founding"],
        source_fields=["instructor_profiles.is_founding_instructor"],
        related_metrics=["founding.cap"],
    ),
    "search.zero_result": MCPMetricDefinition(
        metric="search.zero_result",
        definition="Search query that returned zero results.",
        requirements=["result_count=0"],
        source_fields=["search_queries.result_count"],
        related_metrics=["search.conversion"],
    ),
    "search.conversion": MCPMetricDefinition(
        metric="search.conversion",
        definition="Search that led to a booking action.",
        requirements=["Search click action = 'book'"],
        source_fields=["search_clicks.action"],
        related_metrics=["search.zero_result"],
    ),
    "booking.completed": MCPMetricDefinition(
        metric="booking.completed",
        definition="Lesson finished successfully.",
        requirements=["status='COMPLETED'"],
        source_fields=["bookings.status"],
        related_metrics=["booking.cancelled", "booking.no_show"],
    ),
    "booking.cancelled": MCPMetricDefinition(
        metric="booking.cancelled",
        definition="Booking was cancelled.",
        requirements=["status='CANCELLED'"],
        source_fields=["bookings.status"],
        related_metrics=["booking.completed", "booking.no_show"],
    ),
    "booking.no_show": MCPMetricDefinition(
        metric="booking.no_show",
        definition="Booking marked as no-show.",
        requirements=["status='NO_SHOW'"],
        source_fields=["bookings.status"],
        related_metrics=["booking.completed", "booking.cancelled"],
    ),
}


@router.get(
    "/{metric_name}",
    response_model=MCPMetricResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_metric_definition(
    metric_name: str,
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
) -> MCPMetricResponse:
    definition = METRIC_DEFINITIONS.get(metric_name)
    if not definition:
        raise HTTPException(status_code=404, detail="metric_not_found")

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(
            id=principal.id,
            email=principal.identifier,
            principal_type=principal.principal_type,
        ),
    )

    return MCPMetricResponse(meta=meta, data=definition)
