"""
Base schemas with standardized field types for consistent API responses.
"""
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic_core import core_schema


class StandardizedModel(BaseModel):  # type: ignore[misc]
    """Base model with standardized JSON encoding"""

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)


class StrictModel(BaseModel):  # type: ignore[misc]
    """Opt-in strict base: forbid extras, validate defaults and assignments.

    This is off by default for existing models. Adopt per-DTO to harden.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
        validate_assignment=True,
    )


class Money(Decimal):
    """Money field that always serializes as float"""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        from pydantic_core import core_schema

        def validate_money(value: Any) -> Decimal:
            if isinstance(value, (int, float)):
                return cls(str(value))
            if isinstance(value, str):
                return cls(value)
            if isinstance(value, Decimal):
                return value
            raise ValueError(f"Cannot convert {type(value)} to Money")

        return core_schema.no_info_after_validator_function(
            validate_money,
            core_schema.union_schema(
                [
                    core_schema.int_schema(),
                    core_schema.float_schema(),
                    core_schema.str_schema(),
                    core_schema.is_instance_schema(Decimal),
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                float,
                info_arg=False,
                return_schema=core_schema.float_schema(),
            ),
        )
