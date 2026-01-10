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

    NOTE: All routes have been migrated to /api/v1/* as of Phase 2 infrastructure migration.
    The only non-v1 routes should be documentation paths and the root path.
    """
    excluded_prefixes = (
        "/docs",
        "/redoc",
        "/openapi",
    )

    if path == "/" or path == "":
        return True

    return any(path.startswith(prefix) for prefix in excluded_prefixes)


class TestRoutingInvariants:
    """Test suite for routing architectural invariants."""

    def test_all_json_routes_under_api_v1(self):
        """
        Ensure all JSON API endpoints are under /api/v1.

        Currently enforced only for fully migrated domains (instructors).
        Bookings domain is in migration - legacy routes exist temporarily.

        This ensures:
        - Clean versioned API surface for new endpoints
        - No ambiguity about which endpoints are current
        - Easy migration path for clients
        """
        routes = _get_api_routes()
        non_v1_routes = []

        # Domains that have been FULLY migrated to v1 (no legacy routes allowed)
        fully_migrated_domains = [
            "/instructors/",  # Should no longer exist as legacy
            "/api/instructors/",  # Should no longer exist as legacy
            "/bookings/",  # Phase 9: Should no longer exist as legacy
            "/api/bookings/",  # Phase 9: Should no longer exist as legacy
            "/messages/",  # Phase 10: Should no longer exist as legacy
            "/api/messages/",  # Phase 10: Should no longer exist as legacy
            "/services/",  # Phase 13: Should no longer exist as legacy
            "/api/favorites/",  # Phase 13: Should no longer exist as legacy
        ]

        # Domains in migration (legacy routes temporarily allowed)
        # Phase 9: Bookings migration complete - no legacy routes allowed
        migrating_domains_legacy_allowed: list[str] = [
            # All bookings and instructor_bookings domains are now fully migrated
            # No legacy routes are allowed for these domains anymore
        ]

        for route in routes:
            path = route.path

            # Skip excluded paths
            if _is_excluded_path(path):
                continue

            # Skip paths that are in migrating domains (temporarily allowed)
            is_migrating_domain = False
            for domain in migrating_domains_legacy_allowed:
                if path.startswith(domain):
                    is_migrating_domain = True
                    break

            if is_migrating_domain:
                continue

            # Check if this is a fully migrated domain (strict check)
            is_fully_migrated_domain = False
            for domain in fully_migrated_domains:
                if path.startswith(domain):
                    is_fully_migrated_domain = True
                    break

            # Only fail if it's a fully migrated domain that's not using v1
            if is_fully_migrated_domain and not path.startswith("/api/v1"):
                non_v1_routes.append(path)

        if non_v1_routes:
            error_msg = (
                f"Found {len(non_v1_routes)} routes in fully migrated domains not using /api/v1. "
                "All endpoints in fully migrated domains must be under /api/v1/*.\n"
                "Fully migrated domains: instructors\n"
                "Non-compliant routes:\n"
            )
            for path in sorted(non_v1_routes):
                error_msg += f"  - {path}\n"

            pytest.fail(error_msg)

    def test_no_trailing_slashes(self):
        """
        Ensure no route paths end with trailing slashes (except root).

        Currently enforced only for v1 routes. Legacy routes will be
        cleaned up in future phases.

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

            # Only enforce for v1 routes (new architecture)
            if not path.startswith("/api/v1"):
                continue

            if path.endswith("/"):
                trailing_slash_routes.append(path)

        if trailing_slash_routes:
            error_msg = (
                f"Found {len(trailing_slash_routes)} v1 routes with trailing slashes.\n"
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
        Currently only enforced for v1 routes.
        """
        routes = _get_api_routes()
        # Only check v1 routes for conflicts
        v1_paths = [route.path for route in routes if route.path.startswith("/api/v1")]
        conflicts = []

        # Known safe conflicts (static route defined before dynamic)
        allowed_conflicts = {
            ("/api/v1/instructors/me", "/api/v1/instructors/{instructor_id}"),
            ("/api/v1/instructors/{instructor_id}", "/api/v1/instructors/me"),
            # The static "me" route is defined before the dynamic {instructor_id} route
            # in the v1 router, so FastAPI correctly matches "me" first.
            # Bookings v1: Static routes defined before dynamic {booking_id}
            ("/api/v1/bookings/upcoming", "/api/v1/bookings/{booking_id}"),
            ("/api/v1/bookings/{booking_id}", "/api/v1/bookings/upcoming"),
            ("/api/v1/bookings/stats", "/api/v1/bookings/{booking_id}"),
            ("/api/v1/bookings/{booking_id}", "/api/v1/bookings/stats"),
            ("/api/v1/bookings/check-availability", "/api/v1/bookings/{booking_id}"),
            ("/api/v1/bookings/{booking_id}", "/api/v1/bookings/check-availability"),
            ("/api/v1/bookings/send-reminders", "/api/v1/bookings/{booking_id}"),
            ("/api/v1/bookings/{booking_id}", "/api/v1/bookings/send-reminders"),
            # Admin bookings: static stats route defined before dynamic booking_id route
            ("/api/v1/admin/bookings/stats", "/api/v1/admin/bookings/{booking_id}"),
            ("/api/v1/admin/bookings/{booking_id}", "/api/v1/admin/bookings/stats"),
            # Pricing endpoint uses same {booking_id} path parameter
            ("/api/v1/bookings/{booking_id}/pricing", "/api/v1/bookings/{booking_id}/preview"),
            ("/api/v1/bookings/{booking_id}/preview", "/api/v1/bookings/{booking_id}/pricing"),
            # Messages v1: Static routes defined before dynamic {message_id}
            # Phase 10: /config, /unread-count, /mark-read, /send, /stream defined before /{message_id}
            ("/api/v1/messages/config", "/api/v1/messages/{message_id}"),
            ("/api/v1/messages/{message_id}", "/api/v1/messages/config"),
            ("/api/v1/messages/unread-count", "/api/v1/messages/{message_id}"),
            ("/api/v1/messages/{message_id}", "/api/v1/messages/unread-count"),
            ("/api/v1/messages/mark-read", "/api/v1/messages/{message_id}"),
            ("/api/v1/messages/{message_id}", "/api/v1/messages/mark-read"),
            # Phase 2: /stream (per-user SSE) defined before /{message_id}
            ("/api/v1/messages/stream", "/api/v1/messages/{message_id}"),
            ("/api/v1/messages/{message_id}", "/api/v1/messages/stream"),
            # Notifications v1: static routes defined before dynamic {notification_id}
            ("/api/v1/notifications/unread-count", "/api/v1/notifications/{notification_id}"),
            ("/api/v1/notifications/{notification_id}", "/api/v1/notifications/unread-count"),
            ("/api/v1/notifications/read-all", "/api/v1/notifications/{notification_id}"),
            ("/api/v1/notifications/{notification_id}", "/api/v1/notifications/read-all"),
            # Reviews v1: Static routes defined before dynamic {booking_id}
            ("/api/v1/reviews/booking/existing", "/api/v1/reviews/booking/{booking_id}"),
            ("/api/v1/reviews/booking/{booking_id}", "/api/v1/reviews/booking/existing"),
            # Search history v1: Static routes defined before dynamic {search_id}
            # Phase 14: /guest and /interaction defined before /{search_id}
            ("/api/v1/search-history/guest", "/api/v1/search-history/{search_id}"),
            ("/api/v1/search-history/{search_id}", "/api/v1/search-history/guest"),
            ("/api/v1/search-history/interaction", "/api/v1/search-history/{search_id}"),
            ("/api/v1/search-history/{search_id}", "/api/v1/search-history/interaction"),
            # Phase 23: Availability v1 routes - prefix-based routing with /instructors/availability
            # The availability router is mounted with prefix "/instructors/availability" which is more
            # specific than the instructors router prefix "/instructors" with /{instructor_id}
            ("/api/v1/instructors/{instructor_id}", "/api/v1/instructors/availability"),
            ("/api/v1/instructors/availability", "/api/v1/instructors/{instructor_id}"),
            # Availability router: Static routes defined before dynamic {window_id}
            # The static routes (week, copy-week, etc.) are defined before /{window_id}
            ("/api/v1/instructors/availability/week", "/api/v1/instructors/availability/{window_id}"),
            ("/api/v1/instructors/availability/{window_id}", "/api/v1/instructors/availability/week"),
            ("/api/v1/instructors/availability/copy-week", "/api/v1/instructors/availability/{window_id}"),
            ("/api/v1/instructors/availability/{window_id}", "/api/v1/instructors/availability/copy-week"),
            ("/api/v1/instructors/availability/apply-to-date-range", "/api/v1/instructors/availability/{window_id}"),
            ("/api/v1/instructors/availability/{window_id}", "/api/v1/instructors/availability/apply-to-date-range"),
            ("/api/v1/instructors/availability/specific-date", "/api/v1/instructors/availability/{window_id}"),
            ("/api/v1/instructors/availability/{window_id}", "/api/v1/instructors/availability/specific-date"),
            ("/api/v1/instructors/availability/bulk-update", "/api/v1/instructors/availability/{window_id}"),
            ("/api/v1/instructors/availability/{window_id}", "/api/v1/instructors/availability/bulk-update"),
            ("/api/v1/instructors/availability/blackout-dates", "/api/v1/instructors/availability/{window_id}"),
            ("/api/v1/instructors/availability/{window_id}", "/api/v1/instructors/availability/blackout-dates"),
            # Admin auth-blocks: /summary static route defined before /{email} dynamic route
            ("/api/v1/admin/auth-blocks/summary", "/api/v1/admin/auth-blocks/{email}"),
            ("/api/v1/admin/auth-blocks/{email}", "/api/v1/admin/auth-blocks/summary"),
        }

        for path1, path2 in combinations(v1_paths, 2):
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
                    # Check if this is an allowed conflict
                    if (path1, path2) not in allowed_conflicts and (path2, path1) not in allowed_conflicts:
                        conflicts.append((path1, path2))

        if conflicts:
            error_msg = (
                f"Found {len(conflicts)} potential static/dynamic route conflicts in v1 routes.\n"
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

    def test_v1_bookings_endpoints_exist(self):
        """Verify v1 bookings endpoints are properly mounted."""
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_bookings_endpoints = [
            "/api/v1/bookings",  # GET list, POST create
            "/api/v1/bookings/upcoming",  # GET
            "/api/v1/bookings/stats",  # GET
            "/api/v1/bookings/check-availability",  # POST
            "/api/v1/bookings/{booking_id}",  # GET
            "/api/v1/bookings/{booking_id}/preview",  # GET
            "/api/v1/bookings/{booking_id}/cancel",  # POST
            "/api/v1/bookings/{booking_id}/complete",  # POST
            "/api/v1/bookings/{booking_id}/confirm-payment",  # POST
        ]

        missing = []
        for expected in expected_bookings_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 bookings endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_v1_instructor_bookings_endpoints_exist(self):
        """Verify v1 instructor-bookings endpoints are properly mounted."""
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_instructor_bookings_endpoints = [
            "/api/v1/instructor-bookings",  # GET list
            "/api/v1/instructor-bookings/pending-completion",  # GET
            "/api/v1/instructor-bookings/upcoming",  # GET
            "/api/v1/instructor-bookings/completed",  # GET
            "/api/v1/instructor-bookings/{booking_id}/complete",  # POST
            "/api/v1/instructor-bookings/{booking_id}/dispute",  # POST
        ]

        missing = []
        for expected in expected_instructor_bookings_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 instructor-bookings endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_bookings_endpoints_removed(self):
        """
        Verify legacy bookings endpoints are REMOVED.

        Phase 9: Frontend migration is complete. All bookings endpoints
        must now use /api/v1/bookings and /api/v1/instructor-bookings.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_bookings_endpoints = [
            "/bookings/",
            "/bookings/{booking_id}",
            "/bookings/{booking_id}/preview",
            "/bookings/{booking_id}/cancel",
            "/bookings/{booking_id}/complete",
            "/bookings/{booking_id}/reschedule",
            "/bookings/{booking_id}/confirm-payment",
            "/bookings/{booking_id}/payment-method",
            "/bookings/upcoming",
            "/bookings/stats",
            "/bookings/check-availability",
            "/bookings/send-reminders",
            "/instructors/bookings/",
            "/instructors/bookings/{booking_id}",
            "/instructors/bookings/{booking_id}/complete",
            "/instructors/bookings/{booking_id}/dispute",
            "/instructors/bookings/pending-completion",
            "/instructors/bookings/upcoming",
            "/instructors/bookings/completed",
            "/api/instructors/bookings/",
        ]

        found_legacy = []
        for legacy in legacy_bookings_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy bookings endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/bookings or /api/v1/instructor-bookings instead."
            )

    def test_v1_messages_endpoints_exist(self):
        """
        Verify v1 messages endpoints are properly mounted.

        Phase 10: Messages domain migrated to /api/v1/messages.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_messages_endpoints = [
            "/api/v1/messages/config",  # GET
            "/api/v1/messages/unread-count",  # GET
            "/api/v1/messages/mark-read",  # POST
            "/api/v1/messages/stream",  # GET (SSE - per-user inbox, Phase 2)
            "/api/v1/messages/{message_id}",  # PATCH, DELETE
            "/api/v1/messages/{message_id}/reactions",  # POST, DELETE
        ]

        missing = []
        for expected in expected_messages_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 messages endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_messages_endpoints_removed(self):
        """
        Verify legacy messages endpoints are REMOVED.

        Phase 10: Messages migration is complete. All messages endpoints
        must now use /api/v1/messages.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_messages_endpoints = [
            "/api/messages/config",
            "/api/messages/unread-count",
            "/api/messages/mark-read",
            "/api/messages/send",
            "/api/messages/stream/{booking_id}",
            "/api/messages/history/{booking_id}",
            "/api/messages/typing/{booking_id}",
            "/api/messages/{message_id}",
            "/api/messages/{message_id}/reactions",
        ]

        found_legacy = []
        for legacy in legacy_messages_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy messages endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/messages instead."
            )

    def test_v1_services_endpoints_exist(self):
        """
        Verify v1 services endpoints are properly mounted.

        Phase 13: Services domain migrated to /api/v1/services.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_services_endpoints = [
            "/api/v1/services/categories",  # GET
            "/api/v1/services/catalog",  # GET
            "/api/v1/services/catalog/top-per-category",  # GET
            "/api/v1/services/catalog/all-with-instructors",  # GET
            "/api/v1/services/catalog/kids-available",  # GET
            "/api/v1/services/search",  # GET
            "/api/v1/services/instructor/add",  # POST
        ]

        missing = []
        for expected in expected_services_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 services endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_services_endpoints_removed(self):
        """
        Verify legacy services endpoints are REMOVED.

        Phase 13: Services migration is complete. All services endpoints
        must now use /api/v1/services.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_services_endpoints = [
            "/services/categories",
            "/services/catalog",
            "/services/catalog/top-per-category",
            "/services/catalog/all-with-instructors",
            "/services/catalog/kids-available",
            "/services/search",
            "/services/instructor/add",
        ]

        found_legacy = []
        for legacy in legacy_services_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy services endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/services instead."
            )

    def test_v1_favorites_endpoints_exist(self):
        """
        Verify v1 favorites endpoints are properly mounted.

        Phase 13: Favorites domain migrated to /api/v1/favorites.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_favorites_endpoints = [
            "/api/v1/favorites",  # GET
            "/api/v1/favorites/{instructor_id}",  # POST, DELETE
            "/api/v1/favorites/check/{instructor_id}",  # GET
        ]

        missing = []
        for expected in expected_favorites_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 favorites endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_favorites_endpoints_removed(self):
        """
        Verify legacy favorites endpoints are REMOVED.

        Phase 13: Favorites migration is complete. All favorites endpoints
        must now use /api/v1/favorites.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_favorites_endpoints = [
            "/api/favorites",
            "/api/favorites/{instructor_id}",
            "/api/favorites/check/{instructor_id}",
        ]

        found_legacy = []
        for legacy in legacy_favorites_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy favorites endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/favorites instead."
            )

    def test_v1_search_endpoints_exist(self):
        """
        Verify v1 search endpoints are properly mounted.

        Phase 14: Search domain migrated to /api/v1/search.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_search_endpoints = [
            "/api/v1/search",  # GET - NL search endpoint
        ]

        missing = []
        for expected in expected_search_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 search endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_search_endpoints_removed(self):
        """
        Verify legacy search endpoints are REMOVED.

        Phase 14: Search migration is complete. All search endpoints
        must now use /api/v1/search.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_search_endpoints = [
            "/api/search/instructors",
        ]

        found_legacy = []
        for legacy in legacy_search_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy search endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/search instead."
            )

    def test_v1_search_history_endpoints_exist(self):
        """
        Verify v1 search-history endpoints are properly mounted.

        Phase 14: Search history domain migrated to /api/v1/search-history.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_search_history_endpoints = [
            "/api/v1/search-history",  # GET, POST
            "/api/v1/search-history/guest",  # POST
            "/api/v1/search-history/{search_id}",  # DELETE
            "/api/v1/search-history/interaction",  # POST
        ]

        missing = []
        for expected in expected_search_history_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 search-history endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_search_history_endpoints_removed(self):
        """
        Verify legacy search-history endpoints are REMOVED.

        Phase 14: Search history migration is complete. All search-history endpoints
        must now use /api/v1/search-history.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_search_history_endpoints = [
            "/api/search-history",
            "/api/search-history/",
            "/api/search-history/guest",
            "/api/search-history/{search_id}",
            "/api/search-history/interaction",
        ]

        found_legacy = []
        for legacy in legacy_search_history_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy search-history endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/search-history instead."
            )

    def test_v1_addresses_endpoints_exist(self):
        """
        Verify v1 addresses endpoints are properly mounted.

        Phase 14: Addresses domain migrated to /api/v1/addresses.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_addresses_endpoints = [
            "/api/v1/addresses/zip/is-nyc",  # GET
            "/api/v1/addresses/me",  # GET, POST
            "/api/v1/addresses/me/{address_id}",  # GET, PATCH, DELETE
            "/api/v1/addresses/service-areas/me",  # GET, PUT
            "/api/v1/addresses/places/autocomplete",  # GET
            "/api/v1/addresses/places/details",  # GET
            "/api/v1/addresses/coverage/bulk",  # GET
            "/api/v1/addresses/regions/neighborhoods",  # GET
        ]

        missing = []
        for expected in expected_addresses_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 addresses endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_addresses_endpoints_removed(self):
        """
        Verify legacy addresses endpoints are REMOVED.

        Phase 14: Addresses migration is complete. All addresses endpoints
        must now use /api/v1/addresses.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_addresses_endpoints = [
            "/api/addresses/zip/is-nyc",
            "/api/addresses/me",
            "/api/addresses/me/{address_id}",
            "/api/addresses/service-areas/me",
            "/api/addresses/places/autocomplete",
            "/api/addresses/places/details",
            "/api/addresses/coverage/bulk",
            "/api/addresses/regions/neighborhoods",
        ]

        found_legacy = []
        for legacy in legacy_addresses_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy addresses endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/addresses instead."
            )

    def test_v1_public_endpoints_exist(self):
        """
        Verify v1 public endpoints are properly mounted.

        Phase 18: Public domain migrated to /api/v1/public.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_public_endpoints = [
            "/api/v1/public/session/guest",  # POST
            "/api/v1/public/logout",  # POST
            "/api/v1/public/instructors/{instructor_id}/availability",  # GET
            "/api/v1/public/instructors/{instructor_id}/next-available",  # GET
            "/api/v1/public/referrals/send",  # POST
        ]

        missing = []
        for expected in expected_public_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 public endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_public_endpoints_removed(self):
        """
        Verify legacy public endpoints are REMOVED.

        Phase 18: Public migration is complete. All public endpoints
        must now use /api/v1/public.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_public_endpoints = [
            "/api/public/session/guest",
            "/api/public/logout",
            "/api/public/instructors/{instructor_id}/availability",
            "/api/public/instructors/{instructor_id}/next-available",
            "/api/public/referrals/send",
        ]

        found_legacy = []
        for legacy in legacy_public_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy public endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/public instead."
            )

    def test_v1_privacy_endpoints_exist(self):
        """
        Verify v1 privacy endpoints are properly mounted.

        Phase 18: Privacy domain migrated to /api/v1/privacy.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_privacy_endpoints = [
            "/api/v1/privacy/export/me",  # POST
            "/api/v1/privacy/delete/me",  # DELETE
            "/api/v1/privacy/statistics",  # GET
            "/api/v1/privacy/retention/apply",  # POST
            "/api/v1/privacy/export/user/{user_id}",  # POST (admin)
            "/api/v1/privacy/delete/user/{user_id}",  # DELETE (admin)
        ]

        missing = []
        for expected in expected_privacy_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 privacy endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_privacy_endpoints_removed(self):
        """
        Verify legacy privacy endpoints are REMOVED.

        Phase 18: Privacy migration is complete. All privacy endpoints
        must now use /api/v1/privacy.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_privacy_endpoints = [
            "/api/privacy/export/me",
            "/api/privacy/delete/me",
            "/api/privacy/statistics",
            "/api/privacy/retention/apply",
            "/api/privacy/export/user/{user_id}",
            "/api/privacy/delete/user/{user_id}",
        ]

        found_legacy = []
        for legacy in legacy_privacy_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy privacy endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/privacy instead."
            )

    def test_v1_uploads_endpoints_exist(self):
        """
        Verify v1 uploads endpoints are properly mounted.

        Phase 18: Uploads domain migrated to /api/v1/uploads.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_uploads_endpoints = [
            "/api/v1/uploads/r2/signed-url",  # POST
            "/api/v1/uploads/r2/proxy",  # POST
            "/api/v1/uploads/r2/finalize/profile-picture",  # POST
        ]

        missing = []
        for expected in expected_uploads_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 uploads endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_uploads_endpoints_removed(self):
        """
        Verify legacy uploads endpoints are REMOVED.

        Phase 18: Uploads migration is complete. All uploads endpoints
        must now use /api/v1/uploads.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_uploads_endpoints = [
            "/api/uploads/r2/signed-url",
            "/api/uploads/r2/proxy",
            "/api/uploads/r2/finalize/profile-picture",
        ]

        found_legacy = []
        for legacy in legacy_uploads_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy uploads endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/uploads instead."
            )

    def test_v1_pricing_endpoints_exist(self):
        """
        Verify v1 pricing endpoints are properly mounted.

        Phase 18: Pricing domain migrated to /api/v1/pricing.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_pricing_endpoints = [
            "/api/v1/pricing/preview",  # POST
        ]

        missing = []
        for expected in expected_pricing_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 pricing endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_pricing_endpoints_removed(self):
        """
        Verify legacy pricing endpoints are REMOVED.

        Phase 18: Pricing migration is complete. All pricing endpoints
        must now use /api/v1/pricing.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_pricing_endpoints = [
            "/api/pricing/preview",
        ]

        found_legacy = []
        for legacy in legacy_pricing_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy pricing endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/pricing instead."
            )

    def test_v1_config_endpoints_exist(self):
        """
        Verify v1 config endpoints are properly mounted.

        Phase 18: Config domain migrated to /api/v1/config.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_config_endpoints = [
            "/api/v1/config/pricing",  # GET
        ]

        missing = []
        for expected in expected_config_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 config endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_config_endpoints_removed(self):
        """
        Verify legacy config endpoints are REMOVED.

        Phase 18: Config migration is complete. All config endpoints
        must now use /api/v1/config.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_config_endpoints = [
            "/api/config/pricing",
        ]

        found_legacy = []
        for legacy in legacy_config_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy config endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/config instead."
            )

    def test_v1_student_badges_endpoints_exist(self):
        """
        Verify v1 student-badges endpoints are properly mounted.

        Phase 18: Student badges domain migrated to /api/v1/students/badges.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_badges_endpoints = [
            "/api/v1/students/badges",  # GET
            "/api/v1/students/badges/earned",  # GET
            "/api/v1/students/badges/progress",  # GET
        ]

        missing = []
        for expected in expected_badges_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 student-badges endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_student_badges_endpoints_removed(self):
        """
        Verify legacy student-badges endpoints are REMOVED.

        Phase 18: Student badges migration is complete. All student badges endpoints
        must now use /api/v1/students/badges.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_badges_endpoints = [
            "/api/students/badges",
            "/api/students/badges/earned",
            "/api/students/badges/progress",
        ]

        found_legacy = []
        for legacy in legacy_badges_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy student-badges endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/students/badges instead."
            )

    def test_v1_users_profile_picture_endpoints_exist(self):
        """
        Verify v1 users profile-picture endpoints are properly mounted.

        Phase 18: Users profile-picture domain migrated to /api/v1/users.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_users_endpoints = [
            "/api/v1/users/me/profile-picture",  # DELETE
            "/api/v1/users/{user_id}/profile-picture-url",  # GET
            "/api/v1/users/profile-picture-urls",  # POST
        ]

        missing = []
        for expected in expected_users_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 users profile-picture endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_users_profile_picture_endpoints_removed(self):
        """
        Verify legacy users profile-picture endpoints are REMOVED.

        Phase 18: Users profile-picture migration is complete. All users profile-picture endpoints
        must now use /api/v1/users.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_users_endpoints = [
            "/users/me/profile-picture",
            "/users/{user_id}/profile-picture-url",
            "/users/profile-picture-urls",
        ]

        found_legacy = []
        for legacy in legacy_users_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy users profile-picture endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/users instead."
            )

    def test_v1_admin_config_endpoints_exist(self):
        """
        Verify v1 admin config endpoints are properly mounted.

        Phase 19: Admin config domain migrated to /api/v1/admin/config.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_admin_config_endpoints = [
            "/api/v1/admin/config/pricing",  # GET, PATCH
        ]

        missing = []
        for expected in expected_admin_config_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 admin config endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_admin_config_endpoints_removed(self):
        """
        Verify legacy admin config endpoints are REMOVED.

        Phase 19: Admin config migration is complete. All admin config endpoints
        must now use /api/v1/admin/config.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_admin_config_endpoints = [
            "/api/admin/config/pricing",
        ]

        found_legacy = []
        for legacy in legacy_admin_config_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy admin config endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/admin/config instead."
            )

    def test_v1_admin_audit_endpoints_exist(self):
        """
        Verify v1 admin audit endpoints are properly mounted.

        Phase 19: Admin audit domain migrated to /api/v1/admin/audit.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_admin_audit_endpoints = [
            "/api/v1/admin/audit",  # GET
        ]

        missing = []
        for expected in expected_admin_audit_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 admin audit endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_admin_audit_endpoints_removed(self):
        """
        Verify legacy admin audit endpoints are REMOVED.

        Phase 19: Admin audit migration is complete. All admin audit endpoints
        must now use /api/v1/admin/audit.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_admin_audit_endpoints = [
            "/api/admin/audit",
        ]

        found_legacy = []
        for legacy in legacy_admin_audit_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy admin audit endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/admin/audit instead."
            )

    def test_v1_admin_badges_endpoints_exist(self):
        """
        Verify v1 admin badges endpoints are properly mounted.

        Phase 19: Admin badges domain migrated to /api/v1/admin/badges.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_admin_badges_endpoints = [
            "/api/v1/admin/badges/pending",  # GET
            "/api/v1/admin/badges/{award_id}/confirm",  # POST
            "/api/v1/admin/badges/{award_id}/revoke",  # POST
        ]

        missing = []
        for expected in expected_admin_badges_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 admin badges endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_admin_badges_endpoints_removed(self):
        """
        Verify legacy admin badges endpoints are REMOVED.

        Phase 19: Admin badges migration is complete. All admin badges endpoints
        must now use /api/v1/admin/badges.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_admin_badges_endpoints = [
            "/api/admin/badges/pending",
            "/api/admin/badges/{award_id}/confirm",
            "/api/admin/badges/{award_id}/revoke",
        ]

        found_legacy = []
        for legacy in legacy_admin_badges_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy admin badges endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/admin/badges instead."
            )

    def test_v1_admin_background_checks_endpoints_exist(self):
        """
        Verify v1 admin background-checks endpoints are properly mounted.

        Phase 19: Admin background-checks domain migrated to /api/v1/admin/background-checks.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_admin_bgc_endpoints = [
            "/api/v1/admin/background-checks/review/count",  # GET
            "/api/v1/admin/background-checks/review",  # GET
            "/api/v1/admin/background-checks/counts",  # GET
            "/api/v1/admin/background-checks/cases",  # GET
            "/api/v1/admin/background-checks/history/{instructor_id}",  # GET
            "/api/v1/admin/background-checks/expiring",  # GET
            "/api/v1/admin/background-checks/webhooks",  # GET
            "/api/v1/admin/background-checks/webhooks/stats",  # GET
            "/api/v1/admin/background-checks/{instructor_id}/override",  # POST
            "/api/v1/admin/background-checks/{instructor_id}/dispute/open",  # POST
            "/api/v1/admin/background-checks/{instructor_id}/dispute/resolve",  # POST
            "/api/v1/admin/background-checks/consent/{instructor_id}/latest",  # GET
        ]

        missing = []
        for expected in expected_admin_bgc_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 admin background-checks endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_admin_background_checks_endpoints_removed(self):
        """
        Verify legacy admin background-checks endpoints are REMOVED.

        Phase 19: Admin background-checks migration is complete. All admin bgc endpoints
        must now use /api/v1/admin/background-checks.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_admin_bgc_endpoints = [
            "/api/admin/bgc/review/count",
            "/api/admin/bgc/review",
            "/api/admin/bgc/counts",
            "/api/admin/bgc/cases",
            "/api/admin/bgc/history/{instructor_id}",
            "/api/admin/bgc/expiring",
            "/api/admin/bgc/webhooks",
            "/api/admin/bgc/webhooks/stats",
            "/api/admin/bgc/{instructor_id}/override",
            "/api/admin/bgc/{instructor_id}/dispute/open",
            "/api/admin/bgc/{instructor_id}/dispute/resolve",
            "/api/admin/bgc/consent/{instructor_id}/latest",
        ]

        found_legacy = []
        for legacy in legacy_admin_bgc_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy admin background-checks endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/admin/background-checks instead."
            )

    def test_v1_admin_instructors_endpoints_exist(self):
        """
        Verify v1 admin instructors endpoints are properly mounted.

        Phase 19: Admin instructors domain migrated to /api/v1/admin/instructors.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        expected_admin_instructors_endpoints = [
            "/api/v1/admin/instructors/{instructor_id}",  # GET
        ]

        missing = []
        for expected in expected_admin_instructors_endpoints:
            if expected not in paths:
                missing.append(expected)

        if missing:
            pytest.fail(
                "Missing expected v1 admin instructors endpoints:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def test_legacy_admin_instructors_endpoints_removed(self):
        """
        Verify legacy admin instructors endpoints are REMOVED.

        Phase 19: Admin instructors migration is complete. All admin instructors endpoints
        must now use /api/v1/admin/instructors.
        """
        routes = _get_api_routes()
        paths = {route.path for route in routes}

        # Legacy endpoints that should NO LONGER exist
        legacy_admin_instructors_endpoints = [
            "/api/admin/instructors/{instructor_id}",
        ]

        found_legacy = []
        for legacy in legacy_admin_instructors_endpoints:
            if legacy in paths:
                found_legacy.append(legacy)

        if found_legacy:
            pytest.fail(
                "Found legacy admin instructors endpoints that should be removed:\n"
                + "\n".join(f"  - {path}" for path in found_legacy)
                + "\n\nUse /api/v1/admin/instructors instead."
            )
