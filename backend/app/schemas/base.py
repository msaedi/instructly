"""
Base schemas with standardized field types for consistent API responses.
"""
from decimal import Decimal
from datetime import datetime, date, time
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


class StandardizedModel(BaseModel):
    """Base model with standardized JSON encoding"""
    
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)
    # TODO: Migrate json_encoders to field serializers
# TODO: Remove __get_validators__ method, keep only __get_pydantic_core_schema__
class Money(Decimal):
    """Money field that always serializes as float"""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, (int, float)):
            return cls(str(v))
        if isinstance(v, str):
            return cls(v)
        if isinstance(v, Decimal):
            return v
        raise ValueError(f'Cannot convert {type(v)} to Money')
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.float_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                float,
                info_arg=False,
                return_schema=core_schema.float_schema(),
            ),
        )