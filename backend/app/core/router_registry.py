from __future__ import annotations

import os
from typing import Any, cast

from fastapi import APIRouter, Depends, FastAPI

from app.api.dependencies.authz import public_guard
from app.core.internal_metrics import internal_metrics_router
from app.dependencies.mcp_auth import audit_mcp_request
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
    users as admin_users_v1,
)
from app.routes.v1.admin.mcp import (
    analytics as admin_mcp_analytics_v1,
    audit as admin_mcp_audit_v1,
    booking_actions as admin_mcp_booking_actions_v1,
    booking_detail as admin_mcp_booking_detail_v1,
    celery as admin_mcp_celery_v1,
    communications as admin_mcp_communications_v1,
    founding as admin_mcp_founding_v1,
    instructor_actions as admin_mcp_instructor_actions_v1,
    instructors as admin_mcp_instructors_v1,
    invites as admin_mcp_invites_v1,
    metrics as admin_mcp_metrics_v1,
    operations as admin_mcp_operations_v1,
    payments as admin_mcp_payments_v1,
    refunds as admin_mcp_refunds_v1,
    search as admin_mcp_search_v1,
    services as admin_mcp_services_v1,
    student_actions as admin_mcp_student_actions_v1,
    webhooks as admin_mcp_webhooks_v1,
)

PUBLIC_OPEN_PATHS = {
    "/",
    "/api/v1/health",
    "/api/v1/health/lite",
    "/api/v1/ready",
    "/api/v1/auth/login",
    "/api/v1/auth/login-with-session",
    "/api/v1/auth/register",
    "/api/v1/password-reset/request",
    "/api/v1/password-reset/confirm",
    "/api/v1/2fa/verify-login",
    "/api/v1/referrals/claim",
    "/api/v1/payments/webhooks/stripe",
    "/api/v1/webhooks/hundredms",
    "/api/v1/metrics/prometheus",
}

PUBLIC_OPEN_PREFIXES = (
    "/api/v1/password-reset/verify",
    "/api/v1/r/",
    "/api/v1/instructors",
    "/api/v1/services",
    "/api/v1/catalog",
    "/api/v1/search",
    "/api/v1/addresses/zip",
    "/api/v1/addresses/places",
    "/api/v1/addresses/coverage",
    "/api/v1/addresses/regions",
    "/api/v1/public",
    "/api/v1/config",
    "/api/v1/users/profile-picture",
)

public_guard_dependency = public_guard(
    open_paths=sorted(PUBLIC_OPEN_PATHS),
    open_prefixes=sorted(PUBLIC_OPEN_PREFIXES),
)


def _include(api_v1: APIRouter, router_obj: Any, prefix: str, **kwargs: Any) -> None:
    cast(Any, api_v1).include_router(router_obj, prefix=prefix, **kwargs)


def _mcp_dependencies(enabled: bool) -> list[Any]:
    return [Depends(audit_mcp_request)] if enabled else []


def _register_core_business_routes(api_v1: APIRouter) -> None:
    # Route order matters: the specific availability paths must come before the
    # catch-all instructor routes to avoid collisions.
    _include(api_v1, availability_windows_v1.router, "/instructors/availability")
    _include(api_v1, instructor_bgc_v1.router, "/instructors")
    _include(api_v1, instructors_v1.router, "/instructors")
    _include(api_v1, bookings_v1.router, "/bookings")
    _include(api_v1, instructor_bookings_v1.router, "/instructor-bookings")
    _include(api_v1, messages_v1.router, "/messages")
    _include(api_v1, sse_v1.router, "/sse")
    _include(api_v1, conversations_v1.router, "/conversations")
    _include(api_v1, reviews_v1.router, "/reviews")
    _include(api_v1, services_v1.router, "/services")
    _include(api_v1, catalog_v1.router, "/catalog")
    _include(api_v1, favorites_v1.router, "/favorites")
    _include(api_v1, lessons_v1.router, "/lessons")
    _include(api_v1, addresses_v1.router, "/addresses")
    _include(api_v1, search_v1.router, "/search")
    _include(api_v1, search_history_v1.router, "/search-history")
    _include(api_v1, referrals_v1.router, "/referrals")
    _include(api_v1, instructor_referrals_v1.router, "/instructor-referrals")


def _register_auth_and_user_routes(api_v1: APIRouter) -> None:
    _include(api_v1, account_v1.router, "/account")
    _include(api_v1, password_reset_v1.router, "/password-reset")
    _include(api_v1, two_factor_auth_v1.router, "/2fa")
    _include(api_v1, auth_v1.router, "/auth")
    _include(api_v1, payments_v1.router, "/payments")
    _include(api_v1, uploads_v1.router, "/uploads")
    _include(api_v1, users_v1.router, "/users")
    _include(api_v1, privacy_v1.router, "/privacy")
    _include(api_v1, public_v1.router, "/public")
    _include(api_v1, push_v1.router, "/push")
    _include(api_v1, notifications_v1.router, "/notifications")
    _include(api_v1, notification_preferences_v1.router, "/notification-preferences")
    _include(api_v1, pricing_v1.router, "/pricing")
    _include(api_v1, config_v1.router, "/config")
    _include(api_v1, student_badges_v1.router, "/students/badges")


def _register_admin_routes(api_v1: APIRouter) -> None:
    _include(api_v1, admin_config_v1.router, "/admin/config")
    _include(api_v1, admin_search_config_v1.router, "/admin")
    _include(api_v1, admin_audit_v1.router, "/admin/audit")
    _include(api_v1, admin_badges_v1.router, "/admin/badges")
    _include(api_v1, admin_background_checks_v1.router, "/admin/background-checks")
    _include(api_v1, admin_instructors_v1.router, "/admin/instructors")
    _include(api_v1, admin_auth_blocks_v1.router, "/admin/auth-blocks")
    _include(api_v1, admin_location_learning_v1.router, "/admin/location-learning")
    _include(api_v1, admin_bookings_v1.router, "/admin")
    _include(api_v1, admin_refunds_v1.router, "/admin/bookings")
    _include(api_v1, admin_users_v1.router, "/admin")


def _register_admin_mcp_routes(api_v1: APIRouter, *, include_audit: bool) -> None:
    dependencies = _mcp_dependencies(include_audit)
    _include(api_v1, admin_mcp_founding_v1.router, "/admin/mcp/founding", dependencies=dependencies)
    _include(
        api_v1,
        admin_mcp_instructors_v1.router,
        "/admin/mcp/instructors",
        dependencies=dependencies,
    )
    _include(api_v1, admin_mcp_invites_v1.router, "/admin/mcp/invites", dependencies=dependencies)
    _include(api_v1, admin_mcp_search_v1.router, "/admin/mcp/search", dependencies=dependencies)
    _include(api_v1, admin_mcp_metrics_v1.router, "/admin/mcp/metrics", dependencies=dependencies)
    _include(api_v1, admin_mcp_celery_v1.router, "/admin/mcp/celery", dependencies=dependencies)
    _include(api_v1, admin_mcp_operations_v1.router, "/admin/mcp/ops", dependencies=dependencies)
    _include(api_v1, admin_mcp_analytics_v1.router, "/admin/mcp", dependencies=dependencies)
    _include(api_v1, admin_mcp_booking_detail_v1.router, "/admin/mcp", dependencies=dependencies)
    _include(api_v1, admin_mcp_refunds_v1.router, "/admin/mcp", dependencies=dependencies)
    _include(api_v1, admin_mcp_booking_actions_v1.router, "/admin/mcp", dependencies=dependencies)
    _include(
        api_v1,
        admin_mcp_instructor_actions_v1.router,
        "/admin/mcp",
        dependencies=dependencies,
    )
    _include(api_v1, admin_mcp_student_actions_v1.router, "/admin/mcp", dependencies=dependencies)
    _include(
        api_v1,
        admin_mcp_communications_v1.router,
        "/admin/mcp",
        dependencies=dependencies,
    )
    _include(api_v1, admin_mcp_services_v1.router, "/admin/mcp/services", dependencies=dependencies)
    _include(api_v1, admin_mcp_payments_v1.router, "/admin/mcp/payments", dependencies=dependencies)
    _include(api_v1, admin_mcp_webhooks_v1.router, "/admin/mcp/webhooks", dependencies=dependencies)
    _include(api_v1, admin_mcp_audit_v1.router, "/admin/mcp/audit", dependencies=dependencies)


def _register_webhook_analytics_and_beta_routes(api_v1: APIRouter) -> None:
    _include(api_v1, webhooks_checkr_v1.router, "/webhooks/checkr")
    _include(api_v1, webhooks_hundredms_v1.router, "/webhooks/hundredms")
    _include(api_v1, analytics_v1.router, "/analytics")
    _include(api_v1, codebase_metrics_v1.router, "/analytics/codebase")
    _include(api_v1, redis_monitor_v1.router, "/redis")
    _include(api_v1, database_monitor_v1.router, "/database")
    _include(api_v1, beta_v1.router, "/beta")


def _register_infrastructure_routes(
    api_v1: APIRouter,
    *,
    include_internal_metrics: bool,
    include_metrics_lite: bool,
) -> None:
    _include(api_v1, health_v1.router, "/health")
    _include(api_v1, ready_v1.router, "/ready")
    _include(api_v1, prometheus_v1.router, "/metrics")
    _include(api_v1, gated_v1.router, "/gated")
    _include(api_v1, metrics_v1.router, "/ops")
    if include_metrics_lite:
        _include(api_v1, metrics_v1.metrics_lite_router, "/ops", include_in_schema=False)
    _include(api_v1, monitoring_v1.router, "/monitoring")
    _include(api_v1, alerts_v1.router, "/monitoring/alerts")
    _include(api_v1, internal_v1.router, "/internal")
    if include_internal_metrics:
        _include(api_v1, internal_metrics_router, "/internal")


def _register_referral_routes(api_v1: APIRouter) -> None:
    _include(api_v1, referrals_v1.public_router, "/r")
    _include(api_v1, referrals_v1.admin_router, "/admin/referrals")


def _build_api_v1_router(
    *,
    include_internal_metrics: bool,
    include_metrics_lite: bool,
    include_audit_dependencies: bool,
) -> APIRouter:
    api_v1 = APIRouter(prefix="/api/v1")
    _register_core_business_routes(api_v1)
    _register_auth_and_user_routes(api_v1)
    _register_admin_routes(api_v1)
    _register_admin_mcp_routes(api_v1, include_audit=include_audit_dependencies)
    _register_webhook_analytics_and_beta_routes(api_v1)
    _register_infrastructure_routes(
        api_v1,
        include_internal_metrics=include_internal_metrics,
        include_metrics_lite=include_metrics_lite,
    )
    _register_referral_routes(api_v1)
    return api_v1


def register_all_routers(app: FastAPI) -> None:
    include_metrics_lite = os.getenv("AVAILABILITY_PERF_DEBUG", "0").lower() in {
        "1",
        "true",
        "yes",
    }
    app.include_router(
        _build_api_v1_router(
            include_internal_metrics=True,
            include_metrics_lite=include_metrics_lite,
            include_audit_dependencies=True,
        )
    )


def register_openapi_routers(app: FastAPI) -> None:
    app.include_router(
        _build_api_v1_router(
            include_internal_metrics=False,
            include_metrics_lite=False,
            include_audit_dependencies=False,
        )
    )


__all__ = [
    "PUBLIC_OPEN_PATHS",
    "PUBLIC_OPEN_PREFIXES",
    "public_guard_dependency",
    "register_all_routers",
    "register_openapi_routers",
]
