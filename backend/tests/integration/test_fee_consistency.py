"""
Ensure frontend fallback fees match backend defaults.
"""

from pathlib import Path
import re

import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS


def _extract_fee(content: str, key: str) -> float:
    match = re.search(rf"{re.escape(key)}\s*:\s*([0-9]+(?:\.[0-9]+)?)", content)
    if not match:
        raise AssertionError(f"Missing fallback fee for {key}")
    return float(match.group(1))


def test_frontend_fallback_fees_match_backend_defaults() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    frontend_hook = repo_root / "frontend" / "hooks" / "usePlatformConfig.ts"

    if not frontend_hook.exists():
        pytest.skip("Frontend not available in this test environment")

    content = frontend_hook.read_text()

    tiers = PRICING_DEFAULTS.get("instructor_tiers", [])
    expected = {
        "founding_instructor": float(PRICING_DEFAULTS["founding_instructor_rate_pct"]),
        "tier_1": float(tiers[0]["pct"]),
        "tier_2": float(tiers[1]["pct"]),
        "tier_3": float(tiers[2]["pct"]),
        "student_booking_fee": float(PRICING_DEFAULTS["student_fee_pct"]),
    }

    for key, expected_value in expected.items():
        actual = _extract_fee(content, key)
        assert actual == expected_value, (
            f"Frontend fallback fee for {key} ({actual}) does not match backend ({expected_value})"
        )
