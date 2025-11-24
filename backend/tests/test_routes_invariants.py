# backend/tests/test_routes_invariants.py
"""
Routing Invariants Tests

Ensures API routing follows architectural standards:
1. All JSON endpoints are under /api/v1 (excluding docs/health/internal)
2. No trailing slashes in route paths
3. No static vs dynamic route conflicts

These tests prevent architectural regression and ensure clean API surface.
"""

from itertools import combinations

from fastapi.routing import APIRoute
import pytest

from app.main import fastapi_app


def _get_api_routes():
    """Get all APIRoute instances from the app."""
    return [route for route in fastapi_app.routes if isinstance(route, APIRoute)]


def _segments(path: str):
    """Split path into segments, removing empty strings."""
    return [s for s in path.split("/") if s]


def _is_dynamic(segment: str) -> bool:
    """Check if a path segment is dynamic (contains path parameter)."""
    return segment.startswith("{") and segment.endswith("}")


def _is_excluded_path(path: str) -> bool:
    """
    Check if path is excluded from v1 requirement.

    Excluded paths:
    - Root path "/"
    - Documentation paths (/docs, /redoc, /openapi.json)
    - Health check paths (/health, /ready, /api/health)
    - Internal monitoring (/internal/*, /metrics/*)
    - Legacy non-JSON endpoints (to be migrated later)
    """
    excluded_prefixes = (
        "/docs",
        "/redoc",
        "/openapi",
        "/health",
        "/ready",
        "/internal/",
        "/metrics/",
        "/prometheus/",
        # Legacy paths - will be migrated in later phases
        "/auth/",
        "/bookings/",
        "/api/auth/",
        "/api/bookings/",
        "/api/public/",
        "/api/config/",
        "/api/search/",
        "/api/search-history/",
        "/api/analytics/",
        "/api/privacy/",
        "/api/payments/",
        "/api/favorites/",
        "/api/messages/",
        "/api/uploads/",
        "/api/reviews/",
        "/api/webhooks/",
        "/api/admin/",
        "/api/referrals/",
        "/api/addresses/",
        "/api/services/",
        "/api/availability-windows/",
        "/api/pricing/",
        "/api/instructor/",
        "/api/instructors/bookings/",  # Legacy instructor bookings
        "/instructors/",  # Legacy non-versioned
        "/availability/",
        "/password-reset/",
        "/admin/",
        "/monitoring/",
        "/alerts/",
        "/codebase/",
        "/redis/",
        "/database/",
        "/beta/",
        "/gated/",
        "/r/",  # Referral short links
        "/users/",
        "/student/",
    )

    if path == "/" or path == "":
        return True

    return any(path.startswith(prefix) for prefix in excluded_prefixes)


class TestRoutingInvariants:
    """Test suite for routing architectural invariants."""

    def test_all_json_routes_under_api_v1(self):
        """
        Ensure all JSON API endpoints are under /api/v1.

        This ensures:
        - Clean versioned API surface
        - No ambiguity about which endpoints are current
        - Easy migration path for clients
        """
        routes = _get_api_routes()
        non_v1_routes = []

        for route in routes:
            path = route.path

            # Skip excluded paths
            if _is_excluded_path(path):
                continue

            # JSON endpoints should be under /api/v1
            if not path.startswith("/api/v1"):
                non_v1_routes.append(path)

        if non_v1_routes:
            error_msg = (
                f"Found {len(non_v1_routes)} non-v1 JSON routes. "
                "All JSON endpoints must be under /api/v1.\n"
                "Non-compliant routes:\n"
            )
            for path in sorted(non_v1_routes):
                error_msg += f"  - {path}\n"

            pytest.fail(error_msg)

    def test_no_trailing_slashes(self):
        """
        Ensure no route paths end with trailing slashes (except root).

        Trailing slashes cause:
        - Ambiguity (is /foo same as /foo/?)
        - Redirect issues
        - Cache key problems
        """
        routes = _get_api_routes()
        trailing_slash_routes = []

        for route in routes:
            path = route.path

            # Root path "/" is allowed
            if path == "/" or path == "":
                continue

            if path.endswith("/"):
                trailing_slash_routes.append(path)

        if trailing_slash_routes:
            error_msg = (
                f"Found {len(trailing_slash_routes)} routes with trailing slashes.\n"
                "Routes with trailing slashes:\n"
            )
            for path in sorted(trailing_slash_routes):
                error_msg += f"  - {path}\n"

            pytest.fail(error_msg)

    def test_no_static_dynamic_conflicts(self):
        """
        Detect static vs dynamic path conflicts.

        Example conflicts:
        - /api/v1/instructors/me vs /api/v1/instructors/{id}
          (Static "me" must come BEFORE dynamic "{id}" in route definition)

        This test ensures route order is correct to avoid matching issues.
        """
        routes = _get_api_routes()
        paths = [route.path for route in routes]
        conflicts = []

        for path1, path2 in combinations(paths, 2):
            segments1 = _segments(path1)
            segments2 = _segments(path2)

            # Only compare paths with same number of segments
            if len(segments1) != len(segments2):
                continue

            # Check each segment pair
            has_static_dynamic_mix = False
            for seg1, seg2 in zip(segments1, segments2):
                is_dyn1 = _is_dynamic(seg1)
                is_dyn2 = _is_dynamic(seg2)

                # If one is static and one is dynamic at same position
                if is_dyn1 != is_dyn2:
                    # This is a potential conflict
                    # FastAPI handles this by route order, but we should be aware
                    has_static_dynamic_mix = True
                    break

            if has_static_dynamic_mix:
                # Check if these are actually the same pattern (dangerous)
                static_segments = []
                for seg1, seg2 in zip(segments1, segments2):
                    if not _is_dynamic(seg1) and not _is_dynamic(seg2):
                        if seg1 == seg2:
                            static_segments.append(seg1)
                    elif _is_dynamic(seg1) == _is_dynamic(seg2):
                        static_segments.append(seg1 if not _is_dynamic(seg1) else seg2)

                # If all non-conflicting segments match, this is a real conflict
                if len(static_segments) == len(segments1) - 1:
                    conflicts.append((path1, path2))

        if conflicts:
            error_msg = (
                f"Found {len(conflicts)} potential static/dynamic route conflicts.\n"
                "Conflicting route pairs:\n"
            )
            for path1, path2 in conflicts:
                error_msg += f"  - {path1} vs {path2}\n"

            error_msg += (
                "\nStatic routes (like /me) must be defined BEFORE dynamic routes (like /{id}) "
                "to avoid matching issues."
            )

            pytest.fail(error_msg)

    def test_v1_instructors_endpoints_exist(self):
        """Verify v1 instructor endpoints are properly mounted."""
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_instructor_endpoints = [
            "/api/v1/instructors",  # GET list, POST create (though POST is /me)
            "/api/v1/instructors/me",  # GET, POST, PUT, DELETE
            "/api/v1/instructors/me/go-live",  # POST
            "/api/v1/instructors/{instructor_id}",  # GET
            "/api/v1/instructors/{instructor_id}/coverage",  # GET
        ]

        missing = []
        for expected in expected_instructor_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 instructor endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_instructors_endpoints_removed(self):
        """Verify legacy non-versioned instructor endpoints are removed."""
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        legacy_instructor_endpoints = [
            "/instructors",
            "/instructors/",
            "/instructors/me",
            "/instructors/{instructor_id}",
            "/api/instructors",
            "/api/instructors/",
            "/api/instructors/me",
            "/api/instructors/{instructor_id}",
        ]

        found_legacy = []
        for legacy in legacy_instructor_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy instructor endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/instructors instead."
            )
