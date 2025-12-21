"""Default pricing configuration values."""

from __future__ import annotations

from typing import Any, Dict

PRICING_DEFAULTS: Dict[str, Any] = {
    "student_fee_pct": 0.12,
    "founding_instructor_rate_pct": 0.08,
    "founding_instructor_cap": 100,
    "founding_search_boost": 1.5,
    "instructor_tiers": [
        {"min": 1, "max": 4, "pct": 0.15},
        {"min": 5, "max": 10, "pct": 0.12},
        {"min": 11, "max": None, "pct": 0.10},
    ],
    "tier_activity_window_days": 30,
    "tier_stepdown_max": 1,
    "tier_inactivity_reset_days": 90,
    "price_floor_cents": {"private_in_person": 8000, "private_remote": 6000},
    "student_credit_cycle": {
        "cycle_len": 11,
        "mod10": 5,
        "cents10": 1000,
        "mod20": 0,
        "cents20": 2000,
    },
}
