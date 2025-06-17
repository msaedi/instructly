# backend/app/infrastructure/cache/redis_cache.py
"""
Cache interface for InstaInstru platform.

Currently implements in-memory caching for development.
Will be replaced with DragonflyDB/Redis in production.
"""

import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Simple in-memory cache implementation for development."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttls: Dict[str, float] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        # Check if key exists and hasn't expired
        if key in self._cache:
            if key in self._ttls and time.time() > self._ttls[key]:
                # Expired
                del self._cache[key]
                del self._ttls[key]
                return None
            
            value = self._cache[key]
            logger.debug(f"Cache hit for key: {key}")
            return value
        
        logger.debug(f"Cache miss for key: {key}")
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with optional TTL."""
        self._cache[key] = value
        
        if ttl:
            self._ttls[key] = time.time() + ttl
        
        logger.debug(f"Cached value for key: {key} (TTL: {ttl}s)")
    
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
        if key in self._ttls:
            del self._ttls[key]
        
        logger.debug(f"Deleted cache key: {key}")
    
    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern."""
        # Simple pattern matching (just prefix for now)
        pattern_prefix = pattern.rstrip('*')
        
        keys_to_delete = [
            key for key in self._cache.keys() 
            if key.startswith(pattern_prefix)
        ]
        
        for key in keys_to_delete:
            await self.delete(key)
        
        logger.debug(f"Deleted {len(keys_to_delete)} keys matching pattern: {pattern}")
    
    async def close(self) -> None:
        """Close cache connection (no-op for in-memory)."""
        pass


class RedisCache:
    """
    Redis/DragonflyDB cache implementation.
    
    This will be the production cache when Redis/DragonflyDB is available.
    """
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client = None
        logger.info("RedisCache initialized (not connected)")
    
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            import redis.asyncio as redis
            self.client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.client.ping()
            logger.info("Connected to Redis/DragonflyDB")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using in-memory cache.")
            raise
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.client:
            return None
        
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with optional TTL."""
        if not self.client:
            return
        
        try:
            serialized = json.dumps(value)
            if ttl:
                await self.client.setex(key, ttl, serialized)
            else:
                await self.client.set(key, serialized)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        if not self.client:
            return
        
        try:
            await self.client.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
    
    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern."""
        if not self.client:
            return
        
        try:
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(
                    cursor, match=pattern, count=100
                )
                if keys:
                    await self.client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()


# Global cache instance
_cache_instance: Optional[Any] = None


def get_cache() -> Any:
    """Get the global cache instance."""
    global _cache_instance
    
    if _cache_instance is None:
        # For now, use in-memory cache
        # TODO: Switch to RedisCache when DragonflyDB is set up
        _cache_instance = InMemoryCache()
        logger.info("Using in-memory cache (development mode)")
    
    return _cache_instance


def set_cache(cache_instance: Any) -> None:
    """Set the global cache instance (for testing)."""
    global _cache_instance
    _cache_instance = cache_instance