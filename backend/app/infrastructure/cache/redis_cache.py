# backend/app/infrastructure/cache/redis_cache.py
"""
Cache infrastructure for InstaInstru platform.

This is a temporary in-memory implementation that will be replaced
with DragonflyDB (Redis-compatible) in production.
"""

import logging
from typing import Any, Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    Simple in-memory cache implementation.
    
    This is a placeholder that mimics Redis interface
    for development purposes.
    """
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._expiry: Dict[str, datetime] = {}
        logger.info("InMemoryCache initialized (development mode)")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        # Check if key exists and not expired
        if key in self._cache:
            if key in self._expiry and datetime.now() > self._expiry[key]:
                # Expired - remove it
                del self._cache[key]
                del self._expiry[key]
                return None
            return self._cache[key]
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default 5 minutes)
        """
        self._cache[key] = value
        if ttl > 0:
            self._expiry[key] = datetime.now() + timedelta(seconds=ttl)
        logger.debug(f"Cached {key} with TTL {ttl}s")
    
    def delete(self, key: str) -> None:
        """Delete key from cache."""
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
        logger.debug(f"Deleted cache key: {key}")
    
    def delete_pattern(self, pattern: str) -> None:
        """
        Delete all keys matching pattern.
        
        Args:
            pattern: Redis-style pattern (e.g., "user:*")
        """
        # Simple pattern matching - just support * wildcard
        if '*' in pattern:
            prefix = pattern.replace('*', '')
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
        else:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
        
        for key in keys_to_delete:
            self.delete(key)
        
        logger.debug(f"Deleted {len(keys_to_delete)} keys matching pattern: {pattern}")
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._expiry.clear()
        logger.info("Cache cleared")


# For future Redis/DragonflyDB implementation
class RedisCache:
    """
    Redis-compatible cache implementation.
    
    This will use DragonflyDB in production.
    """
    
    def __init__(self, redis_url: str):
        # TODO: Implement when DragonflyDB is set up
        raise NotImplementedError("RedisCache not yet implemented - use InMemoryCache")


# Singleton instance
_cache_instance: Optional[InMemoryCache] = None


def get_cache() -> InMemoryCache:
    """
    Get cache instance (singleton).
    
    Returns:
        Cache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryCache()
    return _cache_instance


# Alias for compatibility
Cache = InMemoryCache