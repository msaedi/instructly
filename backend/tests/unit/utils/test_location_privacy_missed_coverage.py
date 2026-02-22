"""Tests targeting missed lines in app/utils/location_privacy.py.

Missed lines:
  28: denom == 0 fallback (lat at exactly +/-90 degrees where cos(lat) = 0)
"""
from __future__ import annotations

import math
from unittest.mock import patch

from app.utils.location_privacy import jitter_coordinates


def test_jitter_coordinates_normal() -> None:
    """Normal jitter within expected range."""
    lat, lng = jitter_coordinates(40.7128, -74.0060)
    # Should be within ~50m of original
    assert abs(lat - 40.7128) < 0.001
    assert abs(lng - (-74.0060)) < 0.001


def test_jitter_coordinates_at_pole() -> None:
    """Line 28: lat at 90 degrees => cos(90) = ~0, triggering denom fallback.

    At exactly 90 degrees, cos(radians(90)) is very close to 0 (floating point
    representation of pi/2 makes it ~6.12e-17, not exactly 0). To test the
    denom == 0 branch, we monkeypatch the earth_radius*cos(...) computation
    by replacing `math.cos` at the function level.
    """
    class MockRandom:
        def uniform(self, a, b):
            return (a + b) / 2

    # Instead of patching math.cos (causes recursion), we use a replacement function
    # that intercepts the specific call pattern.
    original_cos = math.cos

    def patched_cos(val):
        # When called with radians(90) => pi/2, return 0 to trigger the branch
        if abs(val - math.pi / 2) < 0.01:
            return 0.0
        return original_cos(val)

    with patch("app.utils.location_privacy._secure_random", MockRandom()):
        # Temporarily replace math.cos in the location_privacy module
        import app.utils.location_privacy as lp
        orig_math_cos = lp.math.cos
        lp.math.cos = patched_cos
        try:
            lat, lng = jitter_coordinates(90.0, 0.0)
            assert isinstance(lat, float)
            assert isinstance(lng, float)
        finally:
            lp.math.cos = orig_math_cos


def test_jitter_coordinates_custom_range() -> None:
    """Test with custom min/max meters."""
    lat, lng = jitter_coordinates(40.7128, -74.0060, min_meters=10.0, max_meters=20.0)
    assert isinstance(lat, float)
    assert isinstance(lng, float)
    # Should still be very close to original
    assert abs(lat - 40.7128) < 0.001
    assert abs(lng - (-74.0060)) < 0.001
