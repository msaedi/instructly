"""
Shared configuration for pre-commit hooks.

This module contains exclusion lists and common settings used by multiple
hook scripts to ensure consistency.
"""

# ============================================================
# Legacy routes - have v1 counterparts, NOT mounted in main.py
# These are excluded from checking to reduce noise in hook output.
#
# Verified: All these routes are commented out in main.py
# ============================================================
EXCLUDED_LEGACY_ROUTES = [
    # Admin routes - v1 counterparts in routes/v1/admin/
    "backend/app/routes/admin_background_checks.py",  # → v1/admin/background_checks.py
    "backend/app/routes/admin_config.py",             # → v1/admin/config.py
    "backend/app/routes/admin_audit.py",              # → v1/admin/audit.py
    "backend/app/routes/admin_badges.py",             # → v1/admin/badges.py
    "backend/app/routes/admin_instructors.py",        # → v1/admin/instructors.py
    # Core routes - v1 counterparts in routes/v1/
    "backend/app/routes/analytics.py",                # → v1/analytics.py
    "backend/app/routes/bookings.py",                 # → v1/bookings.py
    "backend/app/routes/instructor_bookings.py",      # → v1/instructor_bookings.py
    "backend/app/routes/payments.py",                 # → v1/payments.py
    "backend/app/routes/privacy.py",                  # → v1/privacy.py
    "backend/app/routes/public.py",                   # → v1/public.py
    "backend/app/routes/reviews.py",                  # → v1/reviews.py
    "backend/app/routes/search_history.py",           # → v1/search_history.py
    "backend/app/routes/two_factor_auth.py",          # → v1/two_factor_auth.py
    # Other legacy routes with v1 counterparts
    "backend/app/routes/addresses.py",                # → v1/addresses.py
    "backend/app/routes/auth.py",                     # → v1/auth.py
    "backend/app/routes/availability_windows.py",     # → v1/availability_windows.py
    "backend/app/routes/conversations.py",            # → v1/conversations.py
    "backend/app/routes/favorites.py",                # → v1/favorites.py
    "backend/app/routes/instructors.py",              # → v1/instructors.py
    "backend/app/routes/messages.py",                 # → v1/messages.py
    "backend/app/routes/password_reset.py",           # → v1/password_reset.py
    "backend/app/routes/referrals.py",                # → v1/referrals.py
    "backend/app/routes/search.py",                   # → v1/search.py
    "backend/app/routes/services.py",                 # → v1/services.py
    "backend/app/routes/student_badges.py",           # → v1/student_badges.py
    "backend/app/routes/uploads.py",                  # → v1/uploads.py
    "backend/app/routes/account_management.py",       # → v1/account.py
    "backend/app/routes/instructor_background_checks.py",  # → v1/instructor_bgc.py
    "backend/app/routes/pricing_config_public.py",    # → v1/pricing.py
    "backend/app/routes/pricing_preview.py",          # → v1/pricing.py
    "backend/app/routes/stripe_webhooks.py",          # → v1/payments.py (webhooks)
    "backend/app/routes/users_profile_picture.py",    # → v1/users.py
    "backend/app/routes/webhooks_checkr.py",          # → v1/webhooks/checkr.py
]


def is_excluded_legacy_route(filepath: str) -> bool:
    """
    Check if a file is an excluded legacy route.

    Args:
        filepath: Path to the file (can be absolute or relative)

    Returns:
        True if the file should be excluded from checking
    """
    # Normalize path for comparison
    normalized = filepath.replace("\\", "/")

    for excluded in EXCLUDED_LEGACY_ROUTES:
        if normalized.endswith(excluded) or excluded in normalized:
            return True
    return False
