from typing import Any, Callable, ContextManager, Optional, TypeVar, ParamSpec, Concatenate, Dict
import logging
from sqlalchemy.orm import Session

P = ParamSpec("P")
R = TypeVar("R")

class BaseService:
    db: Session
    cache: Optional[Any]
    logger: logging.Logger
    def __init__(self, db: Session, cache: Optional[Any] = ...) -> None: ...
    def transaction(self) -> ContextManager[Session]: ...
    @staticmethod
    def measure_operation(operation_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
    def get_metrics(self) -> Dict[str, Any]: ...
    def reset_metrics(self) -> None: ...
