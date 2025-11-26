# backend/app/openapi_app.py
"""Lightweight FastAPI app for OpenAPI schema generation.

This avoids importing heavyweight production dependencies like prometheus_client,
Sentry, etc. that are not needed for schema generation.
"""

# Import only the routers, not the full main app
from fastapi import APIRouter, FastAPI

from app.routes import (
    # account_management - DEPRECATED, use /api/v1/account instead
    # addresses - DEPRECATED, use /api/v1/addresses instead
    # admin_config - DEPRECATED, use /api/v1/admin/config instead
    alerts,
    analytics,
    # auth - DEPRECATED, use /api/v1/auth instead
    # availability_windows - DEPRECATED, use /api/v1/instructors/availability instead
    beta,
    # bookings - DEPRECATED, use /api/v1/bookings instead
    codebase_metrics,
    database_monitor,
    # favorites - DEPRECATED, use /api/v1/favorites instead
    gated,
    # instructor_bookings - DEPRECATED, use /api/v1/instructor-bookings instead
    # messages - DEPRECATED, use /api/v1/messages instead
    metrics,
    monitoring,
    # password_reset - DEPRECATED, use /api/v1/password-reset instead
    # payments - DEPRECATED, use /api/v1/payments instead
    # privacy - DEPRECATED, use /api/v1/privacy instead
    prometheus,
    # public - DEPRECATED, use /api/v1/public instead
    redis_monitor,
    # referrals - DEPRECATED, use /api/v1/referrals instead
    # reviews - DEPRECATED, use /api/v1/reviews instead
    # search - DEPRECATED, use /api/v1/search instead
    # search_history - DEPRECATED, use /api/v1/search-history instead
    # services - DEPRECATED, use /api/v1/services instead
    # stripe_webhooks - DEPRECATED, use /api/v1/payments/webhooks/stripe instead
    # two_factor_auth - DEPRECATED, use /api/v1/2fa instead
    # uploads - DEPRECATED, use /api/v1/uploads instead
    # users_profile_picture - DEPRECATED, use /api/v1/users instead
)
from app.routes.v1 import (
    account as account_v1,
    addresses as addresses_v1,
    auth as auth_v1,
    availability_windows as availability_windows_v1,
    bookings as bookings_v1,
    config as config_v1,
    favorites as favorites_v1,
    instructor_bgc as instructor_bgc_v1,
    instructor_bookings as instructor_bookings_v1,
    instructors as instructors_v1,
    messages as messages_v1,
    password_reset as password_reset_v1,
    payments as payments_v1,
    pricing as pricing_v1,
    privacy as privacy_v1,
    public as public_v1,
    referrals as referrals_v1,
    reviews as reviews_v1,
    search as search_v1,
    search_history as search_history_v1,
    services as services_v1,
    student_badges as student_badges_v1,
    two_factor_auth as two_factor_auth_v1,
    uploads as uploads_v1,
    users as users_v1,
    webhooks_checkr as webhooks_checkr_v1,
)
from app.routes.v1.admin import (
    audit as admin_audit_v1,
    background_checks as admin_background_checks_v1,
    badges as admin_badges_v1,
    config as admin_config_v1,
    instructors as admin_instructors_v1,
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

    # Create API v1 router
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(instructors_v1.router, prefix="/instructors")  # type: ignore[attr-defined]
    api_v1.include_router(instructor_bgc_v1.router, prefix="/instructors")  # type: ignore[attr-defined]  # BGC endpoints
    api_v1.include_router(availability_windows_v1.router, prefix="/instructors/availability")  # type: ignore[attr-defined]
    api_v1.include_router(bookings_v1.router, prefix="/bookings")  # type: ignore[attr-defined]
    api_v1.include_router(instructor_bookings_v1.router, prefix="/instructor-bookings")  # type: ignore[attr-defined]
    api_v1.include_router(messages_v1.router, prefix="/messages")  # type: ignore[attr-defined]
    api_v1.include_router(reviews_v1.router, prefix="/reviews")  # type: ignore[attr-defined]
    api_v1.include_router(services_v1.router, prefix="/services")  # type: ignore[attr-defined]
    api_v1.include_router(favorites_v1.router, prefix="/favorites")  # type: ignore[attr-defined]
    api_v1.include_router(addresses_v1.router, prefix="/addresses")  # type: ignore[attr-defined]
    api_v1.include_router(search_v1.router, prefix="/search")  # type: ignore[attr-defined]
    api_v1.include_router(search_history_v1.router, prefix="/search-history")  # type: ignore[attr-defined]
    api_v1.include_router(referrals_v1.router, prefix="/referrals")  # type: ignore[attr-defined]
    api_v1.include_router(account_v1.router, prefix="/account")  # type: ignore[attr-defined]
    api_v1.include_router(password_reset_v1.router, prefix="/password-reset")  # type: ignore[attr-defined]
    api_v1.include_router(two_factor_auth_v1.router, prefix="/2fa")  # type: ignore[attr-defined]
    api_v1.include_router(auth_v1.router, prefix="/auth")  # type: ignore[attr-defined]
    api_v1.include_router(payments_v1.router, prefix="/payments")  # type: ignore[attr-defined]
    # Phase 18 v1 routers
    api_v1.include_router(uploads_v1.router, prefix="/uploads")  # type: ignore[attr-defined]
    api_v1.include_router(users_v1.router, prefix="/users")  # type: ignore[attr-defined]
    api_v1.include_router(privacy_v1.router, prefix="/privacy")  # type: ignore[attr-defined]
    api_v1.include_router(public_v1.router, prefix="/public")  # type: ignore[attr-defined]
    api_v1.include_router(pricing_v1.router, prefix="/pricing")  # type: ignore[attr-defined]
    api_v1.include_router(config_v1.router, prefix="/config")  # type: ignore[attr-defined]
    api_v1.include_router(student_badges_v1.router, prefix="/students/badges")  # type: ignore[attr-defined]
    # Phase 19 v1 admin routers
    api_v1.include_router(admin_config_v1.router, prefix="/admin/config")  # type: ignore[attr-defined]
    api_v1.include_router(admin_audit_v1.router, prefix="/admin/audit")  # type: ignore[attr-defined]
    api_v1.include_router(admin_badges_v1.router, prefix="/admin/badges")  # type: ignore[attr-defined]
    api_v1.include_router(admin_background_checks_v1.router, prefix="/admin/background-checks")  # type: ignore[attr-defined]
    api_v1.include_router(admin_instructors_v1.router, prefix="/admin/instructors")  # type: ignore[attr-defined]
    # Phase 23 v1 webhooks router
    api_v1.include_router(webhooks_checkr_v1.router, prefix="/webhooks/checkr")  # type: ignore[attr-defined]

    # Mount v1 API first
    app.include_router(api_v1)

    # Include all routers in the same order as main.py
    # Legacy auth - now /api/v1/auth
    # app.include_router(auth.router)
    # Legacy two_factor_auth - now /api/v1/2fa
    # app.include_router(two_factor_auth.router)
    # Instructors v1 is mounted above in api_v1
    # app.include_router(instructors.router)  # Legacy - now /api/v1/instructors
    # Legacy instructor_bookings - now /api/v1/instructor-bookings
    # app.include_router(instructor_bookings.router)  # Was: /instructors/bookings
    # Legacy account_management - now /api/v1/account
    # app.include_router(account_management.router)  # Was: /api/account
    # Legacy services - now /api/v1/services
    # app.include_router(services.router)  # Was: /services
    # Legacy availability_windows - now /api/v1/instructors/availability
    # app.include_router(availability_windows.router)
    # Legacy password_reset - now /api/v1/password-reset
    # app.include_router(password_reset.router)
    # Legacy bookings - now /api/v1/bookings
    # app.include_router(bookings.router)  # Was: /bookings
    # Legacy favorites - now /api/v1/favorites
    # app.include_router(favorites.router)  # Was: /api/favorites
    # Legacy payments - now /api/v1/payments
    # app.include_router(payments.router)
    # Legacy messages - now /api/v1/messages
    # app.include_router(messages.router)
    app.include_router(metrics.router)
    app.include_router(monitoring.router)
    app.include_router(alerts.router)
    app.include_router(analytics.router, prefix="/api", tags=["analytics"])
    app.include_router(codebase_metrics.router)
    # Legacy public - now /api/v1/public
    # app.include_router(public.router)
    # Legacy referrals - now /api/v1/referrals
    # app.include_router(referrals.public_router)  # Was: /r/{slug}
    # app.include_router(referrals.router)  # Was: /api/referrals
    # app.include_router(referrals.admin_router)  # Was: /api/admin/referrals
    # Mount v1 referrals public router (slug redirect) and admin router
    app.include_router(referrals_v1.public_router)
    app.include_router(referrals_v1.admin_router, prefix="/api/v1/admin/referrals")
    # Legacy search - now /api/v1/search
    # app.include_router(search.router, prefix="/api/search", tags=["search"])
    # Legacy search-history - now /api/v1/search-history
    # app.include_router(search_history.router, prefix="/api/search-history", tags=["search-history"])
    # Legacy addresses - now /api/v1/addresses
    # app.include_router(addresses.router)
    app.include_router(redis_monitor.router)
    app.include_router(database_monitor.router)
    # Legacy admin_config - now /api/v1/admin/config
    # app.include_router(admin_config.router)
    # Legacy privacy - now /api/v1/privacy
    # app.include_router(privacy.router, prefix="/api", tags=["privacy"])
    # Legacy stripe_webhooks - now /api/v1/payments/webhooks/stripe
    # app.include_router(stripe_webhooks.router)
    app.include_router(prometheus.router)
    # Legacy uploads - now /api/v1/uploads
    # app.include_router(uploads.router)
    # Legacy users profile picture - now /api/v1/users
    # app.include_router(users_profile_picture.router)
    app.include_router(beta.router)
    # Legacy reviews - now /api/v1/reviews
    # app.include_router(reviews.router)
    app.include_router(gated.router)

    return app


# Create the app instance
openapi_app = build_openapi_app()
