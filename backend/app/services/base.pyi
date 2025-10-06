import logging
from typing import (
    Any,
    Callable,
    ContextManager,
    Dict,
    Optional,
    ParamSpec,
    Protocol,
    TypedDict,
    TypeVar,
)

from sqlalchemy.orm import Session

P = ParamSpec("P")
R = TypeVar("R")

class AggregatedMetric(TypedDict):
    count: int
    avg_time: float
    min_time: float
    max_time: float
    total_time: float
    success_rate: float
    success_count: int
    failure_count: int


class CacheInvalidationProtocol(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = ...,
        tier: str = ...,
    ) -> bool: ...
    def delete(self, key: str) -> bool: ...
    def delete_pattern(self, pattern: str) -> int: ...


class BaseService:
    db: Session
    cache: Optional[CacheInvalidationProtocol]
    logger: logging.Logger
    def __init__(
        self, db: Session, cache: Optional[CacheInvalidationProtocol] = ...
    ) -> None: ...
    def transaction(self) -> ContextManager[Session]: ...
    @staticmethod
    def measure_operation(
        operation_name: str,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
    def get_metrics(self) -> Dict[str, AggregatedMetric]: ...
    def reset_metrics(self) -> None: ...
    def invalidate_cache(self, *keys: str) -> None: ...
    def invalidate_pattern(self, pattern: str) -> None: ...
    def log_operation(self, operation: str, **context: Any) -> None: ...
