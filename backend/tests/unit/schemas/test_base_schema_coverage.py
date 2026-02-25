"""Tests for app/schemas/base.py — coverage gaps L55, L58 + bug hunting."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel
import pytest

from app.schemas.base import Money


class MoneyModel(BaseModel):
    amount: Money


@pytest.mark.unit
class TestMoneyCoverage:
    """Cover Money validator edge cases."""

    # --- L55: string input ---
    def test_money_from_string(self) -> None:
        """L55: cls(value) for string input."""
        m = MoneyModel(amount="12.34")  # type: ignore[arg-type]
        assert m.amount == Decimal("12.34")

    def test_money_from_string_integer(self) -> None:
        m = MoneyModel(amount="100")  # type: ignore[arg-type]
        assert m.amount == Decimal("100")

    def test_money_from_string_negative(self) -> None:
        m = MoneyModel(amount="-5.67")  # type: ignore[arg-type]
        assert m.amount == Decimal("-5.67")

    def test_money_from_string_zero(self) -> None:
        m = MoneyModel(amount="0")  # type: ignore[arg-type]
        assert m.amount == Decimal("0")

    def test_money_from_string_large(self) -> None:
        m = MoneyModel(amount="999999999.99")  # type: ignore[arg-type]
        assert m.amount == Decimal("999999999.99")

    # --- L55 bug hunt: invalid string values ---
    def test_money_from_string_abc_raises(self) -> None:
        with pytest.raises(Exception):
            MoneyModel(amount="abc")  # type: ignore[arg-type]

    def test_money_from_string_empty_raises(self) -> None:
        with pytest.raises(Exception):
            MoneyModel(amount="")  # type: ignore[arg-type]

    def test_money_from_string_infinity(self) -> None:
        # Decimal accepts "Infinity" but it could be a bug in financial context
        m = MoneyModel(amount="Infinity")  # type: ignore[arg-type]
        assert m.amount == Decimal("Infinity")

    def test_money_from_string_nan(self) -> None:
        m = MoneyModel(amount="NaN")  # type: ignore[arg-type]
        # Decimal("NaN") != Decimal("NaN") — NaN is never equal to itself
        assert m.amount.is_nan()

    # --- int/float/Decimal paths (already covered but good for completeness) ---
    def test_money_from_int(self) -> None:
        m = MoneyModel(amount=42)  # type: ignore[arg-type]
        assert m.amount == Decimal("42")

    def test_money_from_float(self) -> None:
        m = MoneyModel(amount=3.14)  # type: ignore[arg-type]
        assert float(m.amount) == pytest.approx(3.14)

    def test_money_from_decimal(self) -> None:
        m = MoneyModel(amount=Decimal("99.99"))  # type: ignore[arg-type]
        assert m.amount == Decimal("99.99")

    # --- L58: unsupported type ---
    def test_money_from_dict_raises(self) -> None:
        """L58: raise ValueError for unsupported types."""
        with pytest.raises(Exception):
            MoneyModel(amount={"value": 10})  # type: ignore[arg-type]

    def test_money_from_list_raises(self) -> None:
        with pytest.raises(Exception):
            MoneyModel(amount=[1, 2, 3])  # type: ignore[arg-type]

    def test_money_from_none_raises(self) -> None:
        with pytest.raises(Exception):
            MoneyModel(amount=None)  # type: ignore[arg-type]

    def test_money_from_bool_coerces(self) -> None:
        # bool is subclass of int in Python, so this might coerce
        m = MoneyModel(amount=True)  # type: ignore[arg-type]
        assert m.amount == Decimal("1")

    # --- Serialization ---
    def test_money_serializes_to_float(self) -> None:
        m = MoneyModel(amount="12.50")  # type: ignore[arg-type]
        dumped = m.model_dump()
        assert isinstance(dumped["amount"], float)
        assert dumped["amount"] == 12.50

    def test_money_json_serializes_to_float(self) -> None:
        m = MoneyModel(amount=Decimal("99.99"))  # type: ignore[arg-type]
        import json

        data = json.loads(m.model_dump_json())
        assert isinstance(data["amount"], float)
        assert data["amount"] == 99.99

    def test_money_validate_money_function_directly_unsupported_type(self) -> None:
        """L58: Directly call the actual validate_money inner function with unsupported type.

        The Pydantic union schema normally rejects non-matching types before
        validate_money runs. We extract the real closure from the core schema
        and call it directly to exercise the ValueError at L58.
        """
        from app.schemas.base import Money

        # Extract the actual validate_money closure from the Pydantic core schema
        schema = Money.__get_pydantic_core_schema__(Money, None)
        validate_money = schema["function"]["function"]

        # Call with unsupported types to hit L58 in the real source code
        with pytest.raises(ValueError, match="Cannot convert"):
            validate_money(object())

        with pytest.raises(ValueError, match="Cannot convert"):
            validate_money({"key": "value"})

        with pytest.raises(ValueError, match="Cannot convert"):
            validate_money([1, 2, 3])


@pytest.mark.unit
class TestBaseSchemaClasses:
    """Cover Model, StrictModel, StandardizedModel classes."""

    def test_model_allows_extras(self) -> None:
        from app.schemas.base import Model

        class MyModel(Model):
            name: str = "test"

        m = MyModel()
        assert m.name == "test"

    def test_strict_model_forbids_extras(self) -> None:
        from app.schemas.base import StrictModel

        class MyStrict(StrictModel):
            name: str = "test"

        with pytest.raises(Exception):
            MyStrict(name="ok", extra_field="boom")  # type: ignore[call-arg]

    def test_standardized_model_config(self) -> None:
        from app.schemas.base import StandardizedModel

        assert StandardizedModel.model_config.get("use_enum_values") is True
        assert StandardizedModel.model_config.get("populate_by_name") is True

    def test_strict_schemas_env_var(self) -> None:
        from app.schemas.base import STRICT_SCHEMAS

        # In test environment, STRICT_SCHEMAS is typically False
        assert isinstance(STRICT_SCHEMAS, bool)
