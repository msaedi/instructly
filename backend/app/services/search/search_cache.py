# backend/app/services/search/search_cache.py
"""
Multi-layer caching for NL search.
Provides response, parsed query, and location caching with version-based invalidation.

Cache Layers:
1. Full Response Cache (5min TTL) - skip entire pipeline
2. Parsed Query Cache (1hr TTL) - skip parsing
3. Embedding Cache (24hr TTL) - handled by EmbeddingService
4. Location Cache (7 days TTL) - skip geocoding
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.services.cache_service import CacheService
    from app.services.search.query_parser import ParsedQuery

logger = logging.getLogger(__name__)

# TTL Configuration (in seconds)
RESPONSE_CACHE_TTL = 60 * 5  # 5 minutes
PARSED_CACHE_TTL = 60 * 60  # 1 hour
LOCATION_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days

# Cache key prefixes
RESPONSE_PREFIX = "search"
PARSED_PREFIX = "parsed"
LOCATION_PREFIX = "geo"
VERSION_KEY = "search:current_version"

# Relative date indicators - queries with these shouldn't be cached
# because the resolved date will be stale the next day
RELATIVE_DATE_INDICATORS = [
    "today",
    "tomorrow",
    "tonight",
    "this week",
    "this weekend",
    "next week",
    "next weekend",
    # Standalone weekday names ("monday") are also relative to "now"
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "next monday",
    "next tuesday",
    "next wednesday",
    "next thursday",
    "next friday",
    "next saturday",
    "next sunday",
]


@dataclass
class CachedLocation:
    """Cached location data from geocoding."""

    lng: float
    lat: float
    borough: Optional[str] = None
    neighborhood: Optional[str] = None


class SearchCacheService:
    """
    Multi-layer cache service for NL search.

    Provides:
    - Full response caching (versioned for easy invalidation)
    - Parsed query caching
    - Location geocode caching

    Uses version-based invalidation for response cache to avoid
    expensive key scanning operations.
    """

    def __init__(
        self, cache_service: Optional["CacheService"] = None, region_code: str = "nyc"
    ) -> None:
        self._cache = cache_service
        self._version_cache: int = 1  # Local version cache for memory fallback
        self._region_code = region_code

    @property
    def cache(self) -> Optional["CacheService"]:
        """Get cache service (lazy initialization not used - must be injected)."""
        return self._cache

    # =========================================================================
    # Response Cache (Versioned)
    # =========================================================================

    def get_cached_response(
        self,
        query: str,
        user_location: Optional[tuple[float, float]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        region_code: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached search response.

        Returns full response dict if cache hit, None if miss.
        """
        if not self.cache:
            return None

        key = self._response_cache_key(
            query, user_location, filters, limit, region_code=region_code
        )

        try:
            cached = self.cache.get(key)
            if cached:
                logger.debug(f"Response cache HIT: {key[:50]}")
                return self._deserialize_response(cached)
        except Exception as e:
            logger.warning(f"Response cache error: {e}")

        return None

    def cache_response(
        self,
        query: str,
        response: Dict[str, Any],
        user_location: Optional[tuple[float, float]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        ttl: Optional[int] = None,
        region_code: str | None = None,
    ) -> bool:
        """
        Cache a search response.

        Skips caching for queries with relative date references (e.g., "tomorrow")
        because the resolved date will be stale the next day.

        Returns True if cached successfully.
        """
        if not self.cache:
            return False

        # Don't cache queries with relative date references
        query_lower = query.lower()
        if any(indicator in query_lower for indicator in RELATIVE_DATE_INDICATORS):
            logger.debug(f"Skipping response cache for relative date query: {query[:30]}")
            return False

        key = self._response_cache_key(
            query, user_location, filters, limit, region_code=region_code
        )

        try:
            serialized = self._serialize_response(response)
            self.cache.set(key, serialized, ttl=ttl or RESPONSE_CACHE_TTL)
            logger.debug(f"Response cached: {key[:50]}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")
            return False

    def _response_cache_key(
        self,
        query: str,
        user_location: Optional[tuple[float, float]],
        filters: Optional[Dict[str, Any]],
        limit: int,
        region_code: str | None = None,
    ) -> str:
        """Generate versioned response cache key."""
        version = self._get_cache_version()
        region = (region_code or self._region_code).lower().strip()

        # Build normalized key data
        # Normalize query: lowercase, strip whitespace, collapse multiple spaces
        normalized_query = " ".join(query.lower().split())
        key_data = {
            "q": normalized_query,
            "loc": f"{user_location[0]:.3f},{user_location[1]:.3f}" if user_location else None,
            "f": json.dumps(filters, sort_keys=True) if filters else None,
            "limit": limit,
            "region": region,
        }

        # Hash the key data
        key_str = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]

        return f"{RESPONSE_PREFIX}:v{version}:{key_hash}"

    def _get_cache_version(self) -> int:
        """Get current cache version."""
        if not self.cache:
            return self._version_cache

        try:
            version = self.cache.get(VERSION_KEY)
            return int(version) if version else 1
        except Exception:
            return 1

    def invalidate_response_cache(self) -> int:
        """
        Invalidate all response cache by incrementing version.

        Returns new version number.
        """
        if not self.cache:
            self._version_cache += 1
            return self._version_cache

        try:
            # Use Redis INCR if available, otherwise get/set
            redis_client = getattr(self.cache, "redis", None)
            if redis_client is not None:
                # Redis INCR is atomic and returns new value
                incr_fn = getattr(redis_client, "incr", None)
                if incr_fn is not None:
                    new_version = incr_fn(VERSION_KEY)
                else:
                    # Fallback if incr not available
                    current = self._get_cache_version()
                    new_version = current + 1
                    self.cache.set(VERSION_KEY, new_version, ttl=60 * 60 * 24 * 30)
            else:
                # Memory fallback: get, increment, set
                current = self._get_cache_version()
                new_version = current + 1
                self.cache.set(VERSION_KEY, new_version, ttl=60 * 60 * 24 * 30)  # 30 days

            logger.info(f"Response cache invalidated, new version: {new_version}")
            return int(new_version)
        except Exception as e:
            logger.error(f"Failed to invalidate cache: {e}")
            return 1

    def _serialize_response(self, response: Dict[str, Any]) -> str:
        """Serialize response for caching."""

        def serialize_value(v: Any) -> Any:
            if isinstance(v, date):
                return v.isoformat()
            if isinstance(v, list):
                return [serialize_value(i) for i in v]
            if isinstance(v, dict):
                return {k: serialize_value(val) for k, val in v.items()}
            return v

        serialized = serialize_value(response)
        return json.dumps(serialized)

    def _deserialize_response(self, cached: Any) -> Dict[str, Any]:
        """Deserialize cached response."""
        if isinstance(cached, str):
            result: Dict[str, Any] = json.loads(cached)
            return result
        if isinstance(cached, dict):
            return cached
        return {}

    # =========================================================================
    # Parsed Query Cache
    # =========================================================================

    def get_cached_parsed_query(
        self,
        query: str,
        region_code: str | None = None,
    ) -> Optional["ParsedQuery"]:
        """
        Get cached parsed query.

        Returns ParsedQuery if cache hit, None if miss.
        """
        if not self.cache:
            return None

        key = self._parsed_cache_key(query, region_code=region_code)

        try:
            cached = self.cache.get(key)
            if cached:
                logger.debug(f"Parsed cache HIT: {query[:30]}")
                return self._deserialize_parsed_query(cached)
        except Exception as e:
            logger.warning(f"Parsed cache error: {e}")

        return None

    def cache_parsed_query(
        self,
        query: str,
        parsed: "ParsedQuery",
        region_code: str | None = None,
    ) -> bool:
        """
        Cache a parsed query.

        Skips caching for queries with relative date references (e.g., "tomorrow")
        because the resolved date will be stale the next day.

        Returns True if cached successfully.
        """
        if not self.cache:
            return False

        # Don't cache queries with relative date references
        query_lower = query.lower()
        if any(indicator in query_lower for indicator in RELATIVE_DATE_INDICATORS):
            logger.debug(f"Skipping cache for relative date query: {query[:30]}")
            return False

        key = self._parsed_cache_key(query, region_code=region_code)

        try:
            serialized = self._serialize_parsed_query(parsed)
            self.cache.set(key, serialized, ttl=PARSED_CACHE_TTL)
            logger.debug(f"Parsed query cached: {query[:30]}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache parsed query: {e}")
            return False

    def _parsed_cache_key(self, query: str, region_code: str | None = None) -> str:
        """Generate parsed query cache key."""
        region = (region_code or self._region_code).lower().strip()
        # Normalize: lowercase, collapse multiple spaces
        normalized = " ".join(query.lower().split())
        key_hash = hashlib.sha256(f"{region}:{normalized}".encode()).hexdigest()[:16]
        return f"{PARSED_PREFIX}:{region}:{key_hash}"

    def _serialize_parsed_query(self, parsed: "ParsedQuery") -> str:
        """Serialize ParsedQuery for caching."""
        data = {
            "original_query": parsed.original_query,
            "corrected_query": parsed.corrected_query,
            "service_query": parsed.service_query,
            "max_price": parsed.max_price,
            "min_price": parsed.min_price,
            "price_intent": parsed.price_intent,
            "date": parsed.date.isoformat() if parsed.date else None,
            "date_range_start": parsed.date_range_start.isoformat()
            if parsed.date_range_start
            else None,
            "date_range_end": parsed.date_range_end.isoformat() if parsed.date_range_end else None,
            "date_type": parsed.date_type,
            "time_after": parsed.time_after,
            "time_before": parsed.time_before,
            "time_window": parsed.time_window,
            "location_text": parsed.location_text,
            "location_type": parsed.location_type,
            "audience_hint": parsed.audience_hint,
            "skill_level": parsed.skill_level,
            "urgency": parsed.urgency,
            "parsing_mode": parsed.parsing_mode,
            "parsing_latency_ms": parsed.parsing_latency_ms,
            "confidence": parsed.confidence,
            "needs_llm": parsed.needs_llm,
        }
        return json.dumps(data)

    def _deserialize_parsed_query(self, cached: Any) -> "ParsedQuery":
        """Deserialize cached ParsedQuery."""
        from app.services.search.query_parser import ParsedQuery

        if isinstance(cached, str):
            data = json.loads(cached)
        else:
            data = cached

        return ParsedQuery(
            original_query=data["original_query"],
            corrected_query=data.get("corrected_query"),
            service_query=data["service_query"],
            max_price=data.get("max_price"),
            min_price=data.get("min_price"),
            price_intent=data.get("price_intent"),
            date=date.fromisoformat(data["date"]) if data.get("date") else None,
            date_range_start=date.fromisoformat(data["date_range_start"])
            if data.get("date_range_start")
            else None,
            date_range_end=date.fromisoformat(data["date_range_end"])
            if data.get("date_range_end")
            else None,
            date_type=data.get("date_type"),
            time_after=data.get("time_after"),
            time_before=data.get("time_before"),
            time_window=data.get("time_window"),
            location_text=data.get("location_text"),
            location_type=data.get("location_type"),
            audience_hint=data.get("audience_hint"),
            skill_level=data.get("skill_level"),
            urgency=data.get("urgency"),
            parsing_mode=data.get("parsing_mode", "regex"),
            parsing_latency_ms=data.get("parsing_latency_ms", 0),
            confidence=data.get("confidence", 0.0),
            needs_llm=data.get("needs_llm", False),
        )

    # =========================================================================
    # Location Cache
    # =========================================================================

    def get_cached_location(
        self,
        location_text: str,
        region_code: str | None = None,
    ) -> Optional[CachedLocation]:
        """
        Get cached location coordinates.

        Returns CachedLocation if cache hit, None if miss.
        """
        if not self.cache:
            return None

        key = self._location_cache_key(location_text, region_code=region_code)

        try:
            cached = self.cache.get(key)
            if cached:
                logger.debug(f"Location cache HIT: {location_text}")
                if isinstance(cached, str):
                    data = json.loads(cached)
                else:
                    data = cached
                return CachedLocation(**data)
        except Exception as e:
            logger.warning(f"Location cache error: {e}")

        return None

    def cache_location(
        self,
        location_text: str,
        location: CachedLocation,
        region_code: str | None = None,
    ) -> bool:
        """
        Cache location coordinates.

        Returns True if cached successfully.
        """
        if not self.cache:
            return False

        key = self._location_cache_key(location_text, region_code=region_code)

        try:
            serialized = json.dumps(asdict(location))
            self.cache.set(key, serialized, ttl=LOCATION_CACHE_TTL)
            logger.debug(f"Location cached: {location_text}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache location: {e}")
            return False

    def _location_cache_key(self, location_text: str, region_code: str | None = None) -> str:
        """Generate location cache key."""
        region = (region_code or self._region_code).lower().strip()
        normalized = location_text.lower().strip()
        return f"{LOCATION_PREFIX}:{region}:{normalized}"

    # =========================================================================
    # Cache Warming
    # =========================================================================

    def warm_location_cache(
        self,
        locations: List[Dict[str, Any]],
    ) -> int:
        """
        Pre-populate location cache with known locations.

        Args:
            locations: List of dicts with name, lng, lat, borough, neighborhood

        Returns:
            Number of locations cached
        """
        if not self.cache:
            return 0

        count = 0
        for loc in locations:
            cached_loc = CachedLocation(
                lng=loc["lng"],
                lat=loc["lat"],
                borough=loc.get("borough"),
                neighborhood=loc.get("neighborhood"),
            )
            if self.cache_location(loc["name"], cached_loc):
                count += 1

        logger.info(f"Warmed location cache with {count} locations")
        return count

    # =========================================================================
    # Cache Statistics
    # =========================================================================

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring.

        Returns dict with version, key counts, etc.
        """
        if not self.cache:
            return {"available": False}

        try:
            version = self._get_cache_version()
            return {
                "available": True,
                "response_cache_version": version,
                "ttls": {
                    "response": RESPONSE_CACHE_TTL,
                    "parsed": PARSED_CACHE_TTL,
                    "location": LOCATION_CACHE_TTL,
                },
            }
        except Exception as e:
            return {"available": False, "error": str(e)}
