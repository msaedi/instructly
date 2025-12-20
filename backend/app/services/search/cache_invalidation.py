# backend/app/services/search/cache_invalidation.py
"""
Cache invalidation triggers for NL search.
Called when data changes that affect search results.

These hooks should be called from service layer CRUD operations
to keep search results fresh.

NOTE: Initialize the cache service at app startup by calling:
    init_search_cache(cache_service)
This ensures proper Redis connection injection.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from app.services.search.search_cache import SearchCacheService

if TYPE_CHECKING:
    from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Global cache service instance (initialized on first use or via init)
_cache_service: Optional[SearchCacheService] = None
_underlying_cache: Optional["CacheService"] = None


def init_search_cache(cache_service: "CacheService") -> None:
    """
    Initialize the search cache with an injected CacheService.

    Call this at app startup to ensure proper Redis connection.

    Args:
        cache_service: The application's CacheService instance
    """
    global _cache_service, _underlying_cache
    _underlying_cache = cache_service
    _cache_service = SearchCacheService(cache_service=cache_service)
    logger.info("Search cache initialized with injected CacheService")


def get_search_cache() -> SearchCacheService:
    """
    Get or create the search cache service.

    If not initialized via init_search_cache(), creates a service
    without a cache (operations will be no-ops but won't fail).
    """
    global _cache_service
    if _cache_service is None:
        logger.warning(
            "Search cache accessed before initialization. "
            "Call init_search_cache(cache_service) at app startup."
        )
        _cache_service = SearchCacheService(cache_service=_underlying_cache)
    return _cache_service


def set_search_cache(cache: SearchCacheService) -> None:
    """Set the search cache service (for testing/dependency injection)."""
    global _cache_service
    _cache_service = cache


def invalidate_on_service_change(
    service_id: str,
    change_type: str = "update",
) -> None:
    """
    Invalidate search cache when a service changes.

    Called from service CRUD operations.

    Args:
        service_id: The service that changed
        change_type: "create", "update", or "delete"
    """
    cache = get_search_cache()
    # Best-effort invalidation. Callers should await this function when possible.
    import asyncio

    async def _invalidate() -> None:
        await cache.invalidate_response_cache()

    asyncio.create_task(_invalidate())
    logger.info(f"Search cache invalidated: service {change_type} ({service_id})")


def invalidate_on_availability_change(
    instructor_id: str,
) -> None:
    """
    Invalidate search cache when instructor availability changes.

    Called from availability update operations.

    Args:
        instructor_id: The instructor whose availability changed
    """
    cache = get_search_cache()
    import asyncio

    async def _invalidate() -> None:
        await cache.invalidate_response_cache()

    asyncio.create_task(_invalidate())
    logger.info(f"Search cache invalidated: availability change ({instructor_id})")


def invalidate_on_price_change(
    instructor_id: str,
    service_id: Optional[str] = None,
) -> None:
    """
    Invalidate search cache when pricing changes.

    Called from pricing update operations.

    Args:
        instructor_id: The instructor whose pricing changed
        service_id: Specific service that changed (optional)
    """
    cache = get_search_cache()
    import asyncio

    async def _invalidate() -> None:
        await cache.invalidate_response_cache()

    asyncio.create_task(_invalidate())
    logger.info(f"Search cache invalidated: price change ({instructor_id})")


def invalidate_on_instructor_profile_change(
    instructor_id: str,
) -> None:
    """
    Invalidate search cache when instructor profile changes.

    Only invalidate if change affects ranking signals (photo, bio, etc).

    Args:
        instructor_id: The instructor whose profile changed
    """
    cache = get_search_cache()
    import asyncio

    async def _invalidate() -> None:
        await cache.invalidate_response_cache()

    asyncio.create_task(_invalidate())
    logger.info(f"Search cache invalidated: profile change ({instructor_id})")


def invalidate_on_review_change(
    instructor_id: str,
    review_id: Optional[str] = None,
) -> None:
    """
    Invalidate search cache when a review is added/updated/deleted.

    Reviews affect quality scores in ranking.

    Args:
        instructor_id: The instructor who received the review
        review_id: The review that changed (optional)
    """
    cache = get_search_cache()
    import asyncio

    async def _invalidate() -> None:
        await cache.invalidate_response_cache()

    asyncio.create_task(_invalidate())
    logger.info(f"Search cache invalidated: review change ({instructor_id})")


async def invalidate_all_search_cache() -> int:
    """
    Force invalidation of all search response caches.

    Use sparingly - typically for admin operations or major data changes.

    Returns:
        New cache version number
    """
    cache = get_search_cache()
    new_version = await cache.invalidate_response_cache()
    logger.info(f"Search cache fully invalidated, new version: {new_version}")
    return new_version
