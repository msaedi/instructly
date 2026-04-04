"""Shared typing helpers for the NL pipeline modules."""

from __future__ import annotations

from contextlib import AbstractContextManager
from logging import Logger
from typing import TYPE_CHECKING, Awaitable, Callable, Protocol, TypeVar

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.services.search.embedding_service import EmbeddingService
    from app.services.search.filter_service import FilterService
    from app.services.search.location_embedding_service import LocationEmbeddingService
    from app.services.search.location_llm_service import LocationLLMService
    from app.services.search.ranking_service import RankingService
    from app.services.search.retriever import PostgresRetriever
    from app.services.search.search_cache import SearchCacheService

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
    search_cache: "SearchCacheService"
    embedding_service: "EmbeddingService"
    retriever: "PostgresRetriever"
    filter_service: "FilterService"
    ranking_service: "RankingService"
    location_embedding_service: "LocationEmbeddingService"
    location_llm_service: "LocationLLMService"
