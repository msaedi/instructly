"""Utilities for location privacy safeguards."""

from __future__ import annotations

import math
import secrets
from typing import Tuple

# Cryptographically secure RNG for privacy-sensitive location jittering
_secure_random = secrets.SystemRandom()


def jitter_coordinates(
    lat: float,
    lng: float,
    *,
    min_meters: float = 25.0,
    max_meters: float = 50.0,
) -> Tuple[float, float]:
    """Return coordinates offset by a random 25-50m jitter for privacy."""
    distance = _secure_random.uniform(min_meters, max_meters)
    angle = _secure_random.uniform(0, 2 * math.pi)

    earth_radius = 6_371_000  # meters
    delta_lat = (distance * math.cos(angle)) / earth_radius * (180 / math.pi)
    denom = earth_radius * math.cos(math.radians(lat))
    if denom == 0:
        denom = earth_radius
    delta_lng = (distance * math.sin(angle)) / denom * (180 / math.pi)

    return (lat + delta_lat, lng + delta_lng)
