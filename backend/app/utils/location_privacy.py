"""Utilities for location privacy safeguards."""

from __future__ import annotations

import math
import random
from typing import Tuple


def jitter_coordinates(
    lat: float,
    lng: float,
    *,
    min_meters: float = 300.0,
    max_meters: float = 500.0,
) -> Tuple[float, float]:
    """Return coordinates offset by a random 300-500m jitter for privacy."""
    distance = random.uniform(min_meters, max_meters)
    angle = random.uniform(0, 2 * math.pi)

    earth_radius = 6_371_000  # meters
    delta_lat = (distance * math.cos(angle)) / earth_radius * (180 / math.pi)
    denom = earth_radius * math.cos(math.radians(lat))
    if denom == 0:
        denom = earth_radius
    delta_lng = (distance * math.sin(angle)) / denom * (180 / math.pi)

    return (lat + delta_lat, lng + delta_lng)
