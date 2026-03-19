from pydantic import ValidationError
import pytest

from app.schemas.booking_rules_config import BookingRulesConfig


def test_booking_rules_config_travel_buffer_message_matches_validator() -> None:
    with pytest.raises(ValidationError, match="Travel buffer must be at least equal to non-travel buffer"):
        BookingRulesConfig(
            default_non_travel_buffer_minutes=30,
            default_travel_buffer_minutes=15,
        )
