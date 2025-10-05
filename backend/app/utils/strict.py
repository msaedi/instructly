"""Helpers for working with strict Pydantic models."""

from typing import Any, Dict, Mapping, Type

from pydantic import BaseModel


def model_filter(model_cls: Type[BaseModel], data: Mapping[str, Any]) -> Dict[str, Any]:
    """Return only the fields accepted by the given model class."""

    allowed = set(model_cls.model_fields.keys())
    return {key: value for key, value in dict(data).items() if key in allowed}
