from __future__ import annotations

import json

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY

from app.models.types import ArrayType, IntegerArrayType, StringArrayType


class DummyDialect:
    def __init__(self, name: str):
        self.name = name

    def type_descriptor(self, value):
        return value


def test_array_type_dialect_impl() -> None:
    array_type = ArrayType()
    assert isinstance(array_type.load_dialect_impl(DummyDialect("postgresql")), ARRAY)
    assert isinstance(array_type.load_dialect_impl(DummyDialect("sqlite")), String)


def test_array_type_process_bind_and_result() -> None:
    array_type = ArrayType()
    dialect = DummyDialect("sqlite")

    bound = array_type.process_bind_param([1, 2], dialect)
    assert json.loads(bound) == [1, 2]

    assert array_type.process_result_value(bound, dialect) == [1, 2]
    assert array_type.process_result_value(None, dialect) is None


def test_integer_array_type_processes_values() -> None:
    array_type = IntegerArrayType()
    dialect = DummyDialect("sqlite")

    bound = array_type.process_bind_param(["1", 2], dialect)
    assert json.loads(bound) == [1, 2]
    bound_single = array_type.process_bind_param("3", dialect)
    assert json.loads(bound_single) == [3]

    assert array_type.process_result_value(bound, dialect) == [1, 2]


def test_string_array_type_processes_values() -> None:
    array_type = StringArrayType()
    dialect = DummyDialect("sqlite")

    bound = array_type.process_bind_param([1, "a"], dialect)
    assert json.loads(bound) == ["1", "a"]

    bound_single = array_type.process_bind_param("x", dialect)
    assert json.loads(bound_single) == ["x"]

    assert array_type.process_result_value(bound, dialect) == ["1", "a"]
