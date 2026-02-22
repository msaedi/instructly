# backend/app/openapi_app.py
"""Lightweight FastAPI app for OpenAPI schema generation.

This avoids importing heavyweight production dependencies like prometheus_client,
Sentry, etc. that are not needed for schema generation.

All routes are under /api/v1/* as of Phase 2 infrastructure migration.
"""

from fastapi import APIRouter, FastAPI

# All routes are now under v1
from app.routes.v1 import (
    account as account_v1,
    addresses as addresses_v1,
    alerts as alerts_v1,
    analytics as analytics_v1,
    auth as auth_v1,
    availability_windows as availability_windows_v1,
    beta as beta_v1,
    bookings as bookings_v1,
    catalog as catalog_v1,
    codebase_metrics as codebase_metrics_v1,
    config as config_v1,
    conversations as conversations_v1,
    database_monitor as database_monitor_v1,
    favorites as favorites_v1,
    gated as gated_v1,
    health as health_v1,
    instructor_bgc as instructor_bgc_v1,
    instructor_bookings as instructor_bookings_v1,
    instructor_referrals as instructor_referrals_v1,
    instructors as instructors_v1,
    internal as internal_v1,
    lessons as lessons_v1,
    messages as messages_v1,
    metrics as metrics_v1,
    monitoring as monitoring_v1,
    notification_preferences as notification_preferences_v1,
    notifications as notifications_v1,
    password_reset as password_reset_v1,
    payments as payments_v1,
    pricing as pricing_v1,
    privacy as privacy_v1,
    prometheus as prometheus_v1,
    public as public_v1,
    push as push_v1,
    ready as ready_v1,
    redis_monitor as redis_monitor_v1,
    referrals as referrals_v1,
    reviews as reviews_v1,
    search as search_v1,
    search_history as search_history_v1,
    services as services_v1,
    sse as sse_v1,
    student_badges as student_badges_v1,
    two_factor_auth as two_factor_auth_v1,
    uploads as uploads_v1,
    users as users_v1,
    webhooks_checkr as webhooks_checkr_v1,
    webhooks_hundredms as webhooks_hundredms_v1,
)
from app.routes.v1.admin import (
    audit as admin_audit_v1,
    auth_blocks as admin_auth_blocks_v1,
    background_checks as admin_background_checks_v1,
    badges as admin_badges_v1,
    bookings as admin_bookings_v1,
    config as admin_config_v1,
    instructors as admin_instructors_v1,
    location_learning as admin_location_learning_v1,
    refunds as admin_refunds_v1,
    search_config as admin_search_config_v1,
)
from app.routes.v1.admin.mcp import (
    analytics as admin_mcp_analytics_v1,
    audit as admin_mcp_audit_v1,
    booking_detail as admin_mcp_booking_detail_v1,
    celery as admin_mcp_celery_v1,
    communications as admin_mcp_communications_v1,
    founding as admin_mcp_founding_v1,
    instructors as admin_mcp_instructors_v1,
    invites as admin_mcp_invites_v1,
    metrics as admin_mcp_metrics_v1,
    operations as admin_mcp_operations_v1,
    payments as admin_mcp_payments_v1,
    refunds as admin_mcp_refunds_v1,
    search as admin_mcp_search_v1,
    services as admin_mcp_services_v1,
    webhooks as admin_mcp_webhooks_v1,
)


def build_openapi_app() -> FastAPI:
    """Build a minimal FastAPI app with all routers for OpenAPI generation."""
    app = FastAPI(
        title="iNSTAiNSTRU API",
        version="1.0.0",
        description="iNSTAiNSTRU - NYC's Premier Instructor Marketplace",
        openapi_url="/openapi.json",
        docs_url=None,  # Don't need docs for schema generation
        redoc_url=None,  # Don't need redoc for schema generation
    )

    # Create API v1 router - ALL routes are under /api/v1/*
    api_v1 = APIRouter(prefix="/api/v1")

    # Infrastructure routes
    api_v1.include_router(health_v1.router, prefix="/health")  # type: ignore[attr-defined]
    api_v1.include_router(ready_v1.router, prefix="/ready")  # type: ignore[attr-defined]
    api_v1.include_router(prometheus_v1.router, prefix="/metrics")  # type: ignore[attr-defined]
    api_v1.include_router(gated_v1.router, prefix="/gated")  # type: ignore[attr-defined]
    api_v1.include_router(metrics_v1.router, prefix="/ops")  # type: ignore[attr-defined]
    api_v1.include_router(monitoring_v1.router, prefix="/monitoring")  # type: ignore[attr-defined]
    api_v1.include_router(alerts_v1.router, prefix="/monitoring/alerts")  # type: ignore[attr-defined]
    api_v1.include_router(internal_v1.router, prefix="/internal")  # type: ignore[attr-defined]

    # Core business routes
    api_v1.include_router(instructors_v1.router, prefix="/instructors")  # type: ignore[attr-defined]
    api_v1.include_router(instructor_bgc_v1.router, prefix="/instructors")  # type: ignore[attr-defined]
    api_v1.include_router(availability_windows_v1.router, prefix="/instructors/availability")  # type: ignore[attr-defined]
    api_v1.include_router(bookings_v1.router, prefix="/bookings")  # type: ignore[attr-defined]
    api_v1.include_router(instructor_bookings_v1.router, prefix="/instructor-bookings")  # type: ignore[attr-defined]
    api_v1.include_router(messages_v1.router, prefix="/messages")  # type: ignore[attr-defined]
    api_v1.include_router(conversations_v1.router, prefix="/conversations")  # type: ignore[attr-defined]
    api_v1.include_router(reviews_v1.router, prefix="/reviews")  # type: ignore[attr-defined]
    api_v1.include_router(services_v1.router, prefix="/services")  # type: ignore[attr-defined]
    api_v1.include_router(catalog_v1.router, prefix="/catalog")  # type: ignore[attr-defined]
    api_v1.include_router(favorites_v1.router, prefix="/favorites")  # type: ignore[attr-defined]
    api_v1.include_router(lessons_v1.router, prefix="/lessons")  # type: ignore[attr-defined]
    api_v1.include_router(addresses_v1.router, prefix="/addresses")  # type: ignore[attr-defined]
    api_v1.include_router(search_v1.router, prefix="/search")  # type: ignore[attr-defined]
    api_v1.include_router(search_history_v1.router, prefix="/search-history")  # type: ignore[attr-defined]
    api_v1.include_router(referrals_v1.router, prefix="/referrals")  # type: ignore[attr-defined]
    api_v1.include_router(instructor_referrals_v1.router, prefix="/instructor-referrals")  # type: ignore[attr-defined]

    # Auth routes
    api_v1.include_router(account_v1.router, prefix="/account")  # type: ignore[attr-defined]
    api_v1.include_router(password_reset_v1.router, prefix="/password-reset")  # type: ignore[attr-defined]
    api_v1.include_router(two_factor_auth_v1.router, prefix="/2fa")  # type: ignore[attr-defined]
    api_v1.include_router(auth_v1.router, prefix="/auth")  # type: ignore[attr-defined]
    api_v1.include_router(sse_v1.router, prefix="/sse")  # type: ignore[attr-defined]

    # Payment routes
    api_v1.include_router(payments_v1.router, prefix="/payments")  # type: ignore[attr-defined]

    # User-facing routes
    api_v1.include_router(uploads_v1.router, prefix="/uploads")  # type: ignore[attr-defined]
    api_v1.include_router(users_v1.router, prefix="/users")  # type: ignore[attr-defined]
    api_v1.include_router(privacy_v1.router, prefix="/privacy")  # type: ignore[attr-defined]
    api_v1.include_router(public_v1.router, prefix="/public")  # type: ignore[attr-defined]
    api_v1.include_router(push_v1.router, prefix="/push")  # type: ignore[attr-defined]
    api_v1.include_router(notifications_v1.router, prefix="/notifications")  # type: ignore[attr-defined]
    api_v1.include_router(  # type: ignore[attr-defined]
        notification_preferences_v1.router,
        prefix="/notification-preferences",
    )
    api_v1.include_router(pricing_v1.router, prefix="/pricing")  # type: ignore[attr-defined]
    api_v1.include_router(config_v1.router, prefix="/config")  # type: ignore[attr-defined]
    api_v1.include_router(student_badges_v1.router, prefix="/students/badges")  # type: ignore[attr-defined]

    # Admin routes
    api_v1.include_router(admin_config_v1.router, prefix="/admin/config")  # type: ignore[attr-defined]
    api_v1.include_router(admin_search_config_v1.router, prefix="/admin")  # type: ignore[attr-defined]
    api_v1.include_router(admin_audit_v1.router, prefix="/admin/audit")  # type: ignore[attr-defined]
    api_v1.include_router(admin_badges_v1.router, prefix="/admin/badges")  # type: ignore[attr-defined]
    api_v1.include_router(admin_background_checks_v1.router, prefix="/admin/background-checks")  # type: ignore[attr-defined]
    api_v1.include_router(admin_instructors_v1.router, prefix="/admin/instructors")  # type: ignore[attr-defined]
    api_v1.include_router(admin_auth_blocks_v1.router, prefix="/admin/auth-blocks")  # type: ignore[attr-defined]
    api_v1.include_router(admin_location_learning_v1.router, prefix="/admin/location-learning")  # type: ignore[attr-defined]
    api_v1.include_router(admin_bookings_v1.router, prefix="/admin")  # type: ignore[attr-defined]
    api_v1.include_router(admin_refunds_v1.router, prefix="/admin/bookings")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_founding_v1.router, prefix="/admin/mcp/founding")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_instructors_v1.router, prefix="/admin/mcp/instructors")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_invites_v1.router, prefix="/admin/mcp/invites")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_search_v1.router, prefix="/admin/mcp/search")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_metrics_v1.router, prefix="/admin/mcp/metrics")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_celery_v1.router, prefix="/admin/mcp/celery")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_operations_v1.router, prefix="/admin/mcp/ops")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_analytics_v1.router, prefix="/admin/mcp")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_communications_v1.router, prefix="/admin/mcp")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_booking_detail_v1.router, prefix="/admin/mcp")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_refunds_v1.router, prefix="/admin/mcp")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_services_v1.router, prefix="/admin/mcp/services")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_payments_v1.router, prefix="/admin/mcp/payments")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_webhooks_v1.router, prefix="/admin/mcp/webhooks")  # type: ignore[attr-defined]
    api_v1.include_router(admin_mcp_audit_v1.router, prefix="/admin/mcp/audit")  # type: ignore[attr-defined]
    api_v1.include_router(referrals_v1.admin_router, prefix="/admin/referrals")  # type: ignore[attr-defined]

    # Webhook routes
    api_v1.include_router(webhooks_checkr_v1.router, prefix="/webhooks/checkr")  # type: ignore[attr-defined]
    api_v1.include_router(webhooks_hundredms_v1.router, prefix="/webhooks/hundredms")  # type: ignore[attr-defined]

    # Monitoring/analytics routes
    api_v1.include_router(analytics_v1.router, prefix="/analytics")  # type: ignore[attr-defined]
    api_v1.include_router(codebase_metrics_v1.router, prefix="/analytics/codebase")  # type: ignore[attr-defined]
    api_v1.include_router(redis_monitor_v1.router, prefix="/redis")  # type: ignore[attr-defined]
    api_v1.include_router(database_monitor_v1.router, prefix="/database")  # type: ignore[attr-defined]
    api_v1.include_router(beta_v1.router, prefix="/beta")  # type: ignore[attr-defined]

    # Referral short URLs - /api/v1/r/{slug}
    api_v1.include_router(referrals_v1.public_router, prefix="/r")  # type: ignore[attr-defined]

    # Mount v1 API
    app.include_router(api_v1)

    return app


# Create the app instance
openapi_app = build_openapi_app()
