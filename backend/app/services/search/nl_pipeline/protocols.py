"""Shared typing helpers for the NL pipeline modules."""

from __future__ import annotations

from contextlib import AbstractContextManager
from logging import Logger
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from sqlalchemy.orm import Session

_T = TypeVar("_T")


class AsyncioLike(Protocol):
    """Subset of the asyncio module used by pipeline helpers."""

    def wait_for(self, fut: Awaitable[_T], timeout: float | None) -> Awaitable[_T]:
        ...

    def to_thread(
        self,
        func: Callable[..., _T],
        /,
        *args: object,
        **kwargs: object,
    ) -> Awaitable[_T]:
        ...


LoggerLike = Logger


DBSessionFactory = Callable[[], AbstractContextManager[Session]]


class SearchServiceLike(Protocol):
    """Subset of the NL search facade accessed by pipeline helpers."""

    _region_code: str
    search_cache: Any
    embedding_service: Any
    retriever: Any
    filter_service: Any
    ranking_service: Any
    location_embedding_service: Any
    location_llm_service: Any
