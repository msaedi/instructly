from pydantic import ValidationError
import pytest

from app.schemas.booking_rules_config import BookingRulesConfig


def test_booking_rules_config_travel_buffer_message_matches_validator() -> None:
    with pytest.raises(ValidationError, match="Travel buffer must be at least equal to non-travel buffer"):
        BookingRulesConfig(
            default_non_travel_buffer_minutes=30,
            default_travel_buffer_minutes=15,
        )


def test_booking_rules_config_travel_buffer_still_requires_absolute_minimum() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 30"):
        BookingRulesConfig(
            default_non_travel_buffer_minutes=10,
            default_travel_buffer_minutes=15,
        )


def test_booking_rules_config_numeric_string_still_enforces_relative_travel_buffer_rule() -> None:
    with pytest.raises(ValidationError, match="Travel buffer must be at least equal to non-travel buffer"):
        BookingRulesConfig(
            default_non_travel_buffer_minutes=45,
            default_travel_buffer_minutes="30",
        )


def test_booking_rules_config_invalid_string_uses_field_validation_not_relative_rule() -> None:
    with pytest.raises(ValidationError) as exc_info:
        BookingRulesConfig(
            default_non_travel_buffer_minutes=30,
            default_travel_buffer_minutes="oops",
        )

    errors = exc_info.value.errors()
    assert errors[0]["type"] == "int_parsing"
    assert "Travel buffer must be at least equal to non-travel buffer" not in str(exc_info.value)


def test_booking_rules_config_boolean_input_fails_field_constraints_without_relative_rule() -> None:
    with pytest.raises(ValidationError) as exc_info:
        BookingRulesConfig(
            default_non_travel_buffer_minutes=30,
            default_travel_buffer_minutes=True,
        )

    errors = exc_info.value.errors()
    assert errors[0]["type"] == "greater_than_equal"
    assert "Travel buffer must be at least equal to non-travel buffer" not in str(exc_info.value)
