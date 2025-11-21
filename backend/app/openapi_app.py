# backend/app/openapi_app.py
"""Lightweight FastAPI app for OpenAPI schema generation.

This avoids importing heavyweight production dependencies like prometheus_client,
Sentry, etc. that are not needed for schema generation.
"""

from fastapi import FastAPI

# Import only the routers, not the full main app
from app.routes import (
    account_management,
    addresses,
    admin_config,
    alerts,
    analytics,
    auth,
    availability_windows,
    beta,
    bookings,
    codebase_metrics,
    database_monitor,
    favorites,
    gated,
    instructor_bookings,
    instructors,
    messages,
    metrics,
    monitoring,
    password_reset,
    payments,
    privacy,
    prometheus,
    public,
    redis_monitor,
    referrals,
    reviews,
    search,
    search_history,
    services,
    stripe_webhooks,
    two_factor_auth,
    uploads,
    users_profile_picture,
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

    # Include all routers in the same order as main.py
    app.include_router(auth.router)
    app.include_router(two_factor_auth.router)
    app.include_router(instructors.router)
    app.include_router(instructor_bookings.router)
    app.include_router(account_management.router)
    app.include_router(services.router)
    app.include_router(availability_windows.router)
    app.include_router(password_reset.router)
    app.include_router(bookings.router)
    app.include_router(favorites.router)
    app.include_router(payments.router)
    app.include_router(messages.router)
    app.include_router(metrics.router)
    app.include_router(monitoring.router)
    app.include_router(alerts.router)
    app.include_router(analytics.router, prefix="/api", tags=["analytics"])
    app.include_router(codebase_metrics.router)
    app.include_router(public.router)
    app.include_router(referrals.public_router)
    app.include_router(referrals.router)
    app.include_router(referrals.admin_router)
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(search_history.router, prefix="/api/search-history", tags=["search-history"])
    app.include_router(addresses.router)
    app.include_router(redis_monitor.router)
    app.include_router(database_monitor.router)
    app.include_router(admin_config.router)
    app.include_router(privacy.router, prefix="/api", tags=["privacy"])
    app.include_router(stripe_webhooks.router)
    app.include_router(prometheus.router)
    app.include_router(uploads.router)
    app.include_router(users_profile_picture.router)
    app.include_router(beta.router)
    app.include_router(reviews.router)
    app.include_router(gated.router)

    return app


# Create the app instance
openapi_app = build_openapi_app()
