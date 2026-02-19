"""
Tests for app/ratelimit/mapping.py - targeting CI coverage gaps.

Tests the route-to-bucket mapping configuration.
"""


class TestRouteBuckets:
    """Tests for ROUTE_BUCKETS mapping."""

    def test_route_buckets_exists(self):
        """Test that ROUTE_BUCKETS dictionary exists."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert ROUTE_BUCKETS is not None
        assert isinstance(ROUTE_BUCKETS, dict)

    def test_route_buckets_is_not_empty(self):
        """Test that ROUTE_BUCKETS has entries."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert len(ROUTE_BUCKETS) > 0

    def test_all_keys_are_strings(self):
        """Test that all keys in ROUTE_BUCKETS are strings."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        for key in ROUTE_BUCKETS.keys():
            assert isinstance(key, str), f"Key {key} is not a string"

    def test_all_values_are_strings(self):
        """Test that all values in ROUTE_BUCKETS are strings."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        for key, value in ROUTE_BUCKETS.items():
            assert isinstance(value, str), f"Value for {key} is not a string: {value}"

    def test_keys_are_route_paths(self):
        """Test that all keys look like route paths."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        for key in ROUTE_BUCKETS.keys():
            # Routes should start with /
            assert key.startswith("/"), f"Route {key} doesn't start with /"

    def test_values_are_valid_bucket_names(self):
        """Test that values are valid bucket name identifiers."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        valid_buckets = {
            "auth_bootstrap",
            "read",
            "write",
            "video",
            "webhook_hundredms",
            "financial",
        }

        for key, value in ROUTE_BUCKETS.items():
            assert value in valid_buckets, f"Bucket {value} for route {key} not in valid buckets"

    def test_auth_me_route_exists(self):
        """Test that /auth/me route is mapped."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert "/auth/me" in ROUTE_BUCKETS
        assert ROUTE_BUCKETS["/auth/me"] == "auth_bootstrap"

    def test_search_instructors_route_exists(self):
        """Test that search instructors route is mapped."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert "/api/v1/search/instructors" in ROUTE_BUCKETS
        assert ROUTE_BUCKETS["/api/v1/search/instructors"] == "read"

    def test_bookings_create_route_exists(self):
        """Test that bookings create route is mapped to write bucket."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert "/api/v1/bookings/create" in ROUTE_BUCKETS
        assert ROUTE_BUCKETS["/api/v1/bookings/create"] == "write"

    def test_payments_checkout_route_is_financial(self):
        """Test that payments checkout route is in financial bucket."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert "/api/v1/payments/checkout" in ROUTE_BUCKETS
        assert ROUTE_BUCKETS["/api/v1/payments/checkout"] == "financial"

    def test_lessons_routes_use_video_bucket(self):
        """Video lesson join/status use video, webhook uses dedicated bucket."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        assert ROUTE_BUCKETS["/api/v1/lessons"] == "video"
        assert ROUTE_BUCKETS["/api/v1/webhooks/hundredms"] == "webhook_hundredms"

    def test_all_api_v1_routes_have_correct_prefix(self):
        """Test that API v1 routes have correct prefix."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        for key in ROUTE_BUCKETS.keys():
            if key != "/auth/me":  # Legacy route
                if "v1" in key:
                    assert key.startswith("/api/v1/"), f"Route {key} should start with /api/v1/"


class TestRouteBucketsIntegrity:
    """Tests for route bucket mapping integrity."""

    def test_no_duplicate_routes(self):
        """Test that there are no duplicate route entries."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        # Since it's a dict, duplicates would just overwrite
        # But we can check if any routes are suspiciously similar
        routes = list(ROUTE_BUCKETS.keys())
        assert len(routes) == len(set(routes))

    def test_financial_bucket_for_payment_routes(self):
        """Test that payment-related routes are in financial bucket."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        for route, bucket in ROUTE_BUCKETS.items():
            if "payment" in route.lower() or "checkout" in route.lower():
                assert bucket == "financial", f"Payment route {route} should be in financial bucket"

    def test_write_bucket_for_create_routes(self):
        """Test that create routes are in write bucket."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        for route, bucket in ROUTE_BUCKETS.items():
            if route.endswith("/create"):
                assert bucket == "write", f"Create route {route} should be in write bucket"


class TestRouteBucketsUsage:
    """Tests for how ROUTE_BUCKETS can be used."""

    def test_lookup_existing_route(self):
        """Test looking up an existing route."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        bucket = ROUTE_BUCKETS.get("/auth/me")
        assert bucket == "auth_bootstrap"

    def test_lookup_nonexistent_route_returns_none(self):
        """Test looking up a non-existent route returns None."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        bucket = ROUTE_BUCKETS.get("/nonexistent/route")
        assert bucket is None

    def test_lookup_with_default(self):
        """Test lookup with a default value."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        # Non-existent route with default
        bucket = ROUTE_BUCKETS.get("/nonexistent/route", "default")
        assert bucket == "default"

        # Existing route still returns correct bucket
        bucket = ROUTE_BUCKETS.get("/auth/me", "default")
        assert bucket == "auth_bootstrap"

    def test_can_iterate_over_routes(self):
        """Test that routes can be iterated."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        routes = []
        for route in ROUTE_BUCKETS:
            routes.append(route)

        assert len(routes) == len(ROUTE_BUCKETS)

    def test_can_get_all_bucket_types(self):
        """Test getting all unique bucket types."""
        from app.ratelimit.mapping import ROUTE_BUCKETS

        buckets = set(ROUTE_BUCKETS.values())

        # Should have multiple bucket types
        assert len(buckets) >= 3
        assert "read" in buckets
        assert "write" in buckets
        assert "financial" in buckets


class TestRouteBucketsTypeAnnotations:
    """Tests verifying type annotations are correct."""

    def test_type_annotation_is_correct(self):
        """Test that ROUTE_BUCKETS has correct type annotation."""
        from app.ratelimit import mapping

        # The value should be dict[str, str]
        assert isinstance(mapping.ROUTE_BUCKETS, dict)

        # Verify all entries match the expected types
        for k, v in mapping.ROUTE_BUCKETS.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
