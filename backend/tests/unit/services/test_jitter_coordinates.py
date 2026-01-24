from __future__ import annotations

import math

import pytest

from app.utils.location_privacy import jitter_coordinates


def _haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in meters for two coordinates."""
    earth_radius = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c


@pytest.mark.parametrize(
    ("lat", "lng"),
    [
        (0.0, 0.0),
        (40.7128, -74.0060),
        (51.5074, -0.1278),
        (89.0, 0.0),
        (-45.0, 120.0),
    ],
)
def test_jitter_coordinates_distance_within_bounds(lat: float, lng: float) -> None:
    jittered_lat, jittered_lng = jitter_coordinates(lat, lng)
    distance = _haversine_distance_m(lat, lng, jittered_lat, jittered_lng)

    assert 24 <= distance <= 51


def test_jitter_coordinates_changes_output() -> None:
    lat, lng = 40.7128, -74.0060
    first = jitter_coordinates(lat, lng)
    second = jitter_coordinates(lat, lng)

    assert first != (lat, lng)
    assert second != (lat, lng)
    assert first != second
