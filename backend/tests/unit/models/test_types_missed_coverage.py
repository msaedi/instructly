"""Tests targeting missed lines in app/models/types.py.

Missed lines:
  47: ArrayType.process_bind_param when value is None
  49: ArrayType.process_bind_param when dialect is postgresql
  56: ArrayType.process_result_value when dialect is postgresql
  77: IntegerArrayType.process_bind_param when dialect is postgresql
  87: IntegerArrayType.process_result_value when dialect is postgresql
  92: IntegerArrayType.process_result_value when value is not a string
  127: StringArrayType.process_result_value when value is not a string
"""
from __future__ import annotations

from app.models.types import ArrayType, IntegerArrayType, StringArrayType


class DummyDialect:
    def __init__(self, name: str):
        self.name = name

    def type_descriptor(self, value):
        return value


def test_array_type_bind_none() -> None:
    """Line 47: process_bind_param with None value returns None."""
    at = ArrayType()
    assert at.process_bind_param(None, DummyDialect("sqlite")) is None
    assert at.process_bind_param(None, DummyDialect("postgresql")) is None


def test_array_type_bind_postgresql() -> None:
    """Line 49: process_bind_param with postgresql returns value as-is."""
    at = ArrayType()
    val = [1, 2, 3]
    result = at.process_bind_param(val, DummyDialect("postgresql"))
    assert result is val  # Should return same object


def test_array_type_result_postgresql() -> None:
    """Line 56: process_result_value with postgresql returns value as-is."""
    at = ArrayType()
    val = [1, 2, 3]
    result = at.process_result_value(val, DummyDialect("postgresql"))
    assert result is val


def test_integer_array_type_bind_postgresql() -> None:
    """Line 77: process_bind_param with postgresql returns value as-is."""
    iat = IntegerArrayType()
    val = [10, 20]
    result = iat.process_bind_param(val, DummyDialect("postgresql"))
    assert result is val


def test_integer_array_type_bind_none() -> None:
    """Line 76: IntegerArrayType process_bind_param with None."""
    iat = IntegerArrayType()
    assert iat.process_bind_param(None, DummyDialect("sqlite")) is None


def test_integer_array_type_result_postgresql() -> None:
    """Line 87: process_result_value with postgresql returns value as-is."""
    iat = IntegerArrayType()
    val = [10, 20]
    result = iat.process_result_value(val, DummyDialect("postgresql"))
    assert result is val


def test_integer_array_type_result_non_string() -> None:
    """Line 92: process_result_value with non-string, non-None value."""
    iat = IntegerArrayType()
    val = [1, 2, 3]  # a list, not a string
    result = iat.process_result_value(val, DummyDialect("sqlite"))
    assert result == [1, 2, 3]


def test_string_array_type_result_postgresql() -> None:
    """Line 124 (mirror for StringArrayType): postgresql returns as-is."""
    sat = StringArrayType()
    val = ["a", "b"]
    result = sat.process_result_value(val, DummyDialect("postgresql"))
    assert result is val


def test_string_array_type_result_non_string() -> None:
    """Line 127: process_result_value with non-string, non-None value."""
    sat = StringArrayType()
    val = ["a", "b"]  # a list, not a string
    result = sat.process_result_value(val, DummyDialect("sqlite"))
    assert result == ["a", "b"]


def test_string_array_type_bind_postgresql() -> None:
    """StringArrayType process_bind_param with postgresql returns value as-is."""
    sat = StringArrayType()
    val = ["x", "y"]
    result = sat.process_bind_param(val, DummyDialect("postgresql"))
    assert result is val


def test_string_array_type_bind_none() -> None:
    """StringArrayType process_bind_param with None."""
    sat = StringArrayType()
    assert sat.process_bind_param(None, DummyDialect("sqlite")) is None


def test_integer_array_type_result_none() -> None:
    """IntegerArrayType process_result_value with None."""
    iat = IntegerArrayType()
    assert iat.process_result_value(None, DummyDialect("sqlite")) is None


def test_string_array_type_result_none() -> None:
    """StringArrayType process_result_value with None."""
    sat = StringArrayType()
    assert sat.process_result_value(None, DummyDialect("sqlite")) is None
