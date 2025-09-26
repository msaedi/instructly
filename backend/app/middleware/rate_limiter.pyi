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


class RateLimiter:
    def __init__(self, cache_service: Any | None = ...) -> None: ...

    def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        window_name: str | None = ...,
    ) -> tuple[bool, int, int]: ...

    def reset_limit(self, identifier: str, window_name: str) -> bool: ...

    def get_remaining_requests(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        window_name: str | None = ...,
    ) -> int: ...

    @staticmethod
    def get_rate_limit_stats() -> dict[str, Any]: ...

@overload
def rate_limit(func: Callable[P, R]) -> Callable[P, R]: ...
@overload
def rate_limit(rate_string: str, *, key_type: Any = ..., key_field: str | None = ..., error_message: str | None = ...) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
