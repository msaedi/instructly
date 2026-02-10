from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.schemas.pricing_config import PricingConfig, TierConfig


def _base_payload() -> dict:
    return {
        "student_fee_pct": 0.1,
        "instructor_tiers": [{"min": 0, "max": 9, "pct": 0.2}],
        "tier_activity_window_days": 30,
        "tier_stepdown_max": 1,
        "tier_inactivity_reset_days": 90,
        "price_floor_cents": {"private_in_person": 5000, "private_remote": 4000},
        "student_credit_cycle": {
            "cycle_len": 10,
            "mod10": 0,
            "cents10": 1000,
            "mod20": 0,
            "cents20": 2000,
        },
    }


def test_tier_config_rejects_max_less_than_min():
    with pytest.raises(ValidationError):
        TierConfig(min=10, max=5, pct=0.2)


def test_pricing_config_requires_at_least_one_tier():
    payload = _base_payload()
    payload["instructor_tiers"] = []
    with pytest.raises(ValidationError):
        PricingConfig(**payload)


def test_pricing_config_rejects_non_increasing_tier_mins():
    payload = _base_payload()
    payload["instructor_tiers"] = [
        {"min": 0, "max": 9, "pct": 0.2},
        {"min": 0, "max": 19, "pct": 0.18},
    ]
    with pytest.raises(ValidationError):
        PricingConfig(**payload)


def test_pricing_config_rejects_overlapping_tiers():
    payload = _base_payload()
    payload["instructor_tiers"] = [
        {"min": 0, "max": 10, "pct": 0.2},
        {"min": 10, "max": 20, "pct": 0.18},
    ]
    with pytest.raises(ValidationError):
        PricingConfig(**payload)
