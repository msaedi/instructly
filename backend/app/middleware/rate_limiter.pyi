"""
This is a types-only stub used by mypy; keep in sync with rate_limiter.py (no runtime effect).
"""
from typing import Any, Callable, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")

class RateLimitKeyType:
    IP: Any
    USER: Any
    EMAIL: Any
    ENDPOINT: Any
    COMPOSITE: Any

@overload
def rate_limit(func: Callable[P, R]) -> Callable[P, R]: ...
@overload
def rate_limit(rate_string: str, *, key_type: Any = ..., key_field: str | None = ..., error_message: str | None = ...) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
