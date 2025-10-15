"""Test utilities for pricing expectations derived from configuration."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Tuple

from app.services.config_service import ConfigService


def get_pricing_config(db_session) -> Dict[str, Any]:
    """Return the pricing configuration dict used by the application."""
    config_service = ConfigService(db_session)
    config, _ = config_service.get_pricing_config()
    return config


def cents_from_pct(amount_cents: int, pct_value: float | Decimal) -> int:
    """Convert a percentage value to cents using Decimal for precision."""
    return int(Decimal(amount_cents) * Decimal(str(pct_value)))


def student_fee_cents(db_session, amount_cents: int) -> int:
    """Compute student fee cents for a base amount using configured percentage."""
    config = get_pricing_config(db_session)
    return cents_from_pct(amount_cents, config["student_fee_pct"])


def instructor_tier_pct(db_session, tier_index: int = 0) -> Decimal:
    """Fetch a configured instructor tier percentage as Decimal."""
    config = get_pricing_config(db_session)
    tiers = config.get("instructor_tiers", [])
    if not tiers:
        return Decimal("0")
    pct_value = tiers[min(tier_index, len(tiers) - 1)]["pct"]
    return Decimal(str(pct_value))


def instructor_commission_cents(db_session, amount_cents: int, tier_index: int = 0) -> int:
    """Compute instructor commission cents for a base amount using tier pct."""
    pct = instructor_tier_pct(db_session, tier_index)
    return cents_from_pct(amount_cents, pct)


def default_price_floor_cents(db_session, modality: str) -> Tuple[bool, int]:
    """Return (found, cents) for configured floor by modality name."""
    config = get_pricing_config(db_session)
    key = "private_in_person" if modality == "in_person" else "private_remote"
    floors = config.get("price_floor_cents", {})
    if key not in floors:
        return False, 0
    return True, int(floors[key])
