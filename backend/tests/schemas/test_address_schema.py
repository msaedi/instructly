from pydantic import ValidationError
import pytest

from app.schemas.address import AddressCreate, AddressUpdate


def _base_payload() -> dict:
    return {
        "street_line1": "123 Test St",
        "locality": "New York",
        "administrative_area": "NY",
        "postal_code": "10001",
        "country_code": "US",
    }


def test_address_create_requires_custom_label_for_other() -> None:
    with pytest.raises(ValidationError) as exc:
        AddressCreate(label="other", custom_label="  ", **_base_payload())
    assert "custom_label is required" in str(exc.value)


def test_address_create_trims_custom_label() -> None:
    payload = AddressCreate(label="other", custom_label="  Studio  ", **_base_payload())
    assert payload.custom_label == "Studio"


def test_address_create_rejects_non_string_custom_label() -> None:
    with pytest.raises(ValidationError) as exc:
        AddressCreate(label="other", custom_label=123, **_base_payload())
    assert "custom_label must be a string" in str(exc.value)


def test_address_update_requires_custom_label_for_other() -> None:
    with pytest.raises(ValidationError) as exc:
        AddressUpdate(label="other")
    assert "custom_label is required" in str(exc.value)
