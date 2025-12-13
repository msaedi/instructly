# backend/app/services/search_service.py
"""
Natural Language Search Service for InstaInstru

Provides intelligent search capabilities that understand queries like:
- "piano lessons under $50 today"
- "online math tutoring for high school"
- "yoga classes in Brooklyn this weekend"

This service parses natural language, generates embeddings, and coordinates
with repositories to find the best matches.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, TypedDict, cast

from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from ..repositories.factory import RepositoryFactory
from .base import BaseService
from .review_service import ReviewService

if TYPE_CHECKING:
    from .cache_service import CacheService

logger = logging.getLogger(__name__)

# Search result cache TTL (60 seconds as specified)
SEARCH_CACHE_TTL = 60

# Module-level model cache to avoid reloading on every request
_model_cache: Dict[str, SentenceTransformer] = {}


JsonDict = Dict[str, Any]
JsonList = List[JsonDict]


class ParsedQuery(TypedDict, total=False):
    original_query: str
    cleaned_query: str
    normalized_service: str
    category: str
    is_category_query: bool
    price: JsonDict
    time: JsonDict
    location: JsonDict
    level: JsonDict


def get_cached_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """Get or create a cached sentence transformer model."""
    if model_name not in _model_cache:
        logger.info(f"Loading sentence transformer model: {model_name}")
        _model_cache[model_name] = SentenceTransformer(model_name)
        logger.info(f"Model {model_name} loaded successfully")
    return _model_cache[model_name]


class QueryParser:
    """Parse natural language queries to extract intent and constraints."""

    # Service name normalization (common variations to canonical names)
    SERVICE_ALIASES = {
        # Music
        "keyboard": "Piano",
        "keys": "Piano",
        "drum": "Drums",
        "percussion": "Drums",
        "vocal": "Voice",
        "vocals": "Voice",
        "singing": "Voice",
        "bass": "Bass Guitar",
        # Languages
        "español": "Spanish",
        "mandarin": "Chinese",
        "chinese": "Chinese",
        # Academic
        "sat prep": "SAT Prep",
        "act prep": "ACT Prep",
        "gre prep": "GRE Prep",
        "algebra": "Algebra I",  # Default to Algebra I
        "calculus": "Calculus",
        "calc": "Calculus",
        # Fitness
        "yoga": "Yoga",
        "pilates": "Pilates",
        "martial arts": "Martial Arts",
        "karate": "Martial Arts",
    }

    # Category term mapping
    CATEGORY_TERMS = {
        "music": "Music",
        "language": "Language",
        "languages": "Language",
        "fitness": "Fitness",
        "tutoring": "Academic Tutoring",
        "academic": "Academic Tutoring",
        "test prep": "Test Preparation",
    }

    # Price patterns
    PRICE_PATTERNS = [
        (r"under \$?(\d+)", "max_price"),
        (r"less than \$?(\d+)", "max_price"),
        (r"below \$?(\d+)", "max_price"),
        (r"over \$?(\d+)", "min_price"),
        (r"more than \$?(\d+)", "min_price"),
        (r"above \$?(\d+)", "min_price"),
        (r"between \$?(\d+) and \$?(\d+)", "price_range"),
        (r"\$?(\d+)\s*-\s*\$?(\d+)", "price_range"),
        (r"around \$?(\d+)", "target_price"),
    ]

    # Time patterns
    TIME_PATTERNS = [
        (r"\btoday\b", "today"),
        (r"\btomorrow\b", "tomorrow"),
        (r"\bthis week\b", "this_week"),
        (r"\bnext week\b", "next_week"),
        (r"\bthis weekend\b", "this_weekend"),
        (r"\bnext weekend\b", "next_weekend"),
        (r"\bmonday\b", "monday"),
        (r"\btuesday\b", "tuesday"),
        (r"\bwednesday\b", "wednesday"),
        (r"\bthursday\b", "thursday"),
        (r"\bfriday\b", "friday"),
        (r"\bsaturday\b", "saturday"),
        (r"\bsunday\b", "sunday"),
        (r"\bmorning\b", "morning"),
        (r"\bafternoon\b", "afternoon"),
        (r"\bevening\b", "evening"),
    ]

    # Location patterns
    LOCATION_PATTERNS = [
        (r"\bonline\b", "online"),
        (r"\bvirtual\b", "online"),
        (r"\bremote\b", "online"),
        (r"\bin-person\b", "in_person"),
        (r"\bin person\b", "in_person"),
        (r"\bmanhattan\b", "manhattan"),
        (r"\bbrooklyn\b", "brooklyn"),
        (r"\bqueens\b", "queens"),
        (r"\bbronx\b", "bronx"),
        (r"\bstaten island\b", "staten_island"),
    ]

    # Level patterns
    LEVEL_PATTERNS = [
        (r"\bbeginner\b", "beginner"),
        (r"\bintermediate\b", "intermediate"),
        (r"\badvanced\b", "advanced"),
        (r"\bhigh school\b", "high_school"),
        (r"\bcollege\b", "college"),
        (r"\bAP\b", "ap"),
        (r"\bkids?\b", "kids"),
        (r"\bchildren\b", "kids"),
        (r"\badults?\b", "adults"),
    ]

    # Category patterns (general terms that should return broader results)
    CATEGORY_PATTERNS = [
        r"\bmusic\s+(?:lessons?|classes?|instruction)\b",
        r"\btutoring\s+(?:help|services?)?\b",
        r"\blanguage\s+(?:lessons?|classes?|instruction)\b",
        r"\bfitness\s+(?:classes?|training|instruction)\b",
        r"\barts?\s+(?:lessons?|classes?|instruction)\b",
        r"^(?:lessons?|classes?)\s+(?:under|below|for)",  # Generic "lessons" at start
        # Do NOT classify queries ending in 'teacher' or 'instructor' as category by default
        # We only want explicit category terms/patterns to trigger broader search
    ]

    # Lightweight morphology normalizations (generic)
    MORPH_NORMALIZATIONS = {
        # Plurals → singular
        r"\bclasses\b": "class",
        r"\blessons\b": "lesson",
        r"\bteachers\b": "teacher",
        r"\btutors\b": "tutor",
        r"\binstructors\b": "instructor",
        r"\bcoaches\b": "coach",
        r"\btrainers\b": "trainer",
        # Common verb-noun smoothing (keeps semantics close for catalog names)
        r"\btraining\b": "training",  # noop placeholder for consistency
        r"\btrainer\b": "trainer",
        r"\bcoaching\b": "coaching",
    }

    # Generic role/format stop-words to reduce noise in specific queries
    ROLE_STOPWORDS = [
        r"\bteacher\b",
        r"\btutor\b",
        r"\binstructor\b",
        r"\bcoach\b",
        r"\bclass(?:es)?\b",
        r"\blesson(?:s)?\b",
    ]

    def parse(self, query: str) -> ParsedQuery:
        """
        Parse a natural language query.

        Args:
            query: Natural language search query

        Returns:
            Dictionary with extracted constraints and cleaned query
        """
        query_lower = query.lower()
        cleaned_query = query
        constraints: ParsedQuery = {
            "original_query": query,
            "cleaned_query": cleaned_query,
            "price": {},
            "time": {},
            "location": {},
            "level": {},
        }

        # Extract price constraints
        for pattern, constraint_type in self.PRICE_PATTERNS:
            match = re.search(pattern, query_lower)
            if match:
                if constraint_type == "price_range":
                    constraints["price"]["min"] = float(match.group(1))
                    constraints["price"]["max"] = float(match.group(2))
                elif constraint_type == "target_price":
                    # Around $X means ±20%
                    target = float(match.group(1))
                    constraints["price"]["min"] = target * 0.8
                    constraints["price"]["max"] = target * 1.2
                else:
                    constraints["price"][constraint_type.replace("_price", "")] = float(
                        match.group(1)
                    )

                # Remove price from cleaned query
                cleaned_query = re.sub(pattern, "", cleaned_query)

        # Extract time constraints
        for pattern, time_type in self.TIME_PATTERNS:
            if re.search(pattern, query_lower):
                constraints["time"][time_type] = True
                cleaned_query = re.sub(pattern, "", cleaned_query)

        # Extract location constraints
        for pattern, location_type in self.LOCATION_PATTERNS:
            if re.search(pattern, query_lower):
                constraints["location"][location_type] = True
                cleaned_query = re.sub(pattern, "", cleaned_query)

        # Extract level constraints
        for pattern, level_type in self.LEVEL_PATTERNS:
            if re.search(pattern, query_lower):
                constraints["level"][level_type] = True
                cleaned_query = re.sub(pattern, "", cleaned_query)

        # Clean up whitespace
        cleaned_query = " ".join(cleaned_query.split())

        # Apply lightweight morphology normalizations (generic, not service-specific)
        for pattern, repl in self.MORPH_NORMALIZATIONS.items():
            cleaned_query = re.sub(pattern, repl, cleaned_query, flags=re.IGNORECASE)

        # Remove generic role/format words to improve matching (kept in original_query)
        for pattern in self.ROLE_STOPWORDS:
            cleaned_query = re.sub(pattern, "", cleaned_query, flags=re.IGNORECASE)

        # Final trim
        cleaned_query = " ".join(cleaned_query.split())
        constraints["cleaned_query"] = cleaned_query

        # Normalize service names
        cleaned_lower = cleaned_query.lower()
        for alias, canonical in self.SERVICE_ALIASES.items():
            # Use word boundaries to avoid partial replacements
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, cleaned_lower):
                cleaned_query = re.sub(
                    pattern, canonical.lower(), cleaned_query, flags=re.IGNORECASE
                )
                constraints["cleaned_query"] = cleaned_query
                constraints["normalized_service"] = canonical
                break

        # Check if this is a category query
        constraints["is_category_query"] = False

        # First check for explicit category terms
        for term, category in self.CATEGORY_TERMS.items():
            if term in cleaned_lower:
                constraints["is_category_query"] = True
                constraints["category"] = category
                break

        # Then check category patterns
        if not constraints["is_category_query"]:
            for pattern in self.CATEGORY_PATTERNS:
                if re.search(pattern, query_lower):
                    constraints["is_category_query"] = True
                    break

        return constraints


class SearchService(BaseService):
    """
    Service for natural language search of instructors and services.

    Combines semantic search, constraint filtering, and availability checking
    to provide intelligent search results.
    """

    def __init__(
        self,
        db: Session,
        model_name: str = "all-MiniLM-L6-v2",
        cache_service: Optional["CacheService"] = None,
    ) -> None:
        """
        Initialize search service.

        Args:
            db: Database session
            model_name: Sentence transformer model to use
            cache_service: Optional cache service for result caching
        """
        super().__init__(db)

        # Initialize components
        self.parser = QueryParser()
        self._model_name = model_name
        # Get cached model - loads once, reuses across requests
        self.model: SentenceTransformer = get_cached_model(model_name)
        self.cache_service = cache_service

        # Initialize repositories
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)
        self.analytics_repository = RepositoryFactory.create_service_analytics_repository(db)
        self.instructor_repository = RepositoryFactory.create_instructor_profile_repository(db)
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )
        self.review_service = ReviewService(db)

    def _generate_search_cache_key(self, query: str, limit: int) -> str:
        """Generate a deterministic cache key for search parameters."""
        normalized = {
            "q": query.lower().strip(),
            "limit": limit,
        }
        hash_input = json.dumps(normalized, sort_keys=True)
        return f"search:{hashlib.md5(hash_input.encode()).hexdigest()}"

    @BaseService.measure_operation("natural_language_search")
    def search(self, query: str, limit: int = 20, include_availability: bool = False) -> JsonDict:
        """
        Perform natural language search with caching and stampede protection.

        Uses a lock-based approach to prevent cache stampede (thundering herd):
        - Only ONE request computes the expensive query while others wait
        - Waiting requests check cache after short delay
        - Fallback to compute if lock holder takes too long

        Args:
            query: Natural language search query
            limit: Maximum number of results
            include_availability: Whether to check instructor availability

        Returns:
            Search results with services, instructors, and metadata
        """
        # Try cache first (60-second TTL)
        cache_key = self._generate_search_cache_key(query, limit)
        if self.cache_service and not include_availability:
            cached = self.cache_service.get(cache_key)
            if cached and isinstance(cached, dict):
                logger.debug(f"Search cache hit for query: {query[:30]}...")
                # Add cache hit indicator to metadata
                if "search_metadata" in cached:
                    cached["search_metadata"]["cache_hit"] = True
                return cast(JsonDict, cached)

            # Cache miss - apply stampede protection
            lock_key = f"lock:{cache_key}"
            lock_acquired = self.cache_service.acquire_lock(lock_key, ttl=10)

            if not lock_acquired:
                # Another request is computing - wait and retry cache
                import time

                for retry in range(3):
                    time.sleep(0.1)  # 100ms wait
                    cached = self.cache_service.get(cache_key)
                    if cached and isinstance(cached, dict):
                        logger.debug(f"Search cache hit after wait (retry {retry+1})")
                        if "search_metadata" in cached:
                            cached["search_metadata"]["cache_hit"] = True
                            cached["search_metadata"]["waited_for_lock"] = True
                        return cast(JsonDict, cached)
                # Still no cache after retries - compute anyway (fallback)
                logger.warning(f"Search computing after lock timeout for: {query[:30]}...")

            try:
                # We have the lock (or fallback) - compute the result
                return self._compute_search(query, limit, include_availability, cache_key)
            finally:
                # Release lock if we acquired it
                if lock_acquired:
                    self.cache_service.release_lock(lock_key)

        # No cache service - compute directly without caching
        return self._compute_search(query, limit, include_availability, cache_key=None)

    def _compute_search(
        self,
        query: str,
        limit: int,
        include_availability: bool,
        cache_key: Optional[str],
    ) -> JsonDict:
        """
        Execute the actual search computation (expensive operation).

        This is separated from search() to enable stampede protection -
        only one request computes while others wait for cached result.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            include_availability: Whether to check instructor availability
            cache_key: Cache key to store result (None to skip caching)

        Returns:
            Search results with services, instructors, and metadata
        """
        # Parse the query
        parsed = self.parser.parse(query)
        logger.info(f"Parsed query: {parsed}")

        # Generate embedding for cleaned query (robust to list/ndarray return types)
        cleaned_value = parsed.get("cleaned_query")
        cleaned_query = cleaned_value if isinstance(cleaned_value, str) else ""
        if cleaned_query:
            emb0 = self.model.encode([cleaned_query])[0]
        else:
            # If no service query remains, use full query
            emb0 = self.model.encode([query])[0]

        # Support both numpy arrays (with tolist) and plain Python lists/tuples
        if hasattr(emb0, "tolist"):
            emb_sequence = cast(Sequence[float], emb0.tolist())
        else:
            emb_sequence = cast(Sequence[float], emb0)
        query_embedding: List[float] = list(emb_sequence)

        # Search for services using semantic similarity
        services, observability_candidates = self._search_services(
            query_embedding=query_embedding,
            parsed=parsed,
            limit=limit * 2,  # Get more to filter later
        )

        # Find instructors for matched services
        results = self._find_instructors_for_services(services=services, parsed=parsed, limit=limit)

        # Category fallback: if category query yielded no instructors, broaden within the category
        if parsed.get("is_category_query") and not results:
            try:
                category_name = parsed.get("category")
                if category_name:
                    all_active = self.catalog_repository.get_active_services_with_categories()
                    fallback_services = []
                    for svc in all_active:
                        try:
                            if (
                                svc.category
                                and svc.category.name.lower() == category_name.lower()
                                and any(s.is_active for s in svc.instructor_services)
                            ):
                                svc_dict = svc.to_dict()
                                svc_dict["relevance_score"] = 0.51
                                analytics = self.analytics_repository.get_or_create(svc.id)
                                svc_dict["demand_score"] = analytics.demand_score
                                svc_dict["is_trending"] = analytics.is_trending
                                fallback_services.append(svc_dict)
                        except Exception:
                            continue
                    if fallback_services:
                        results = self._find_instructors_for_services(
                            services=fallback_services[: limit or 10], parsed=parsed, limit=limit
                        )
            except Exception:
                pass

        # Check availability if requested
        if include_availability and parsed.get("time"):
            results = self._filter_by_availability(results, parsed["time"])

        # Track search analytics (log when nothing matched for observability)
        if not services:
            logger.info(
                "NL Search returned no services; consider synonyms or threshold tuning",
                extra={"cleaned_query": parsed.get("cleaned_query")},
            )
            # Return an empty service set gracefully
            empty_response: JsonDict = {
                "query": query,
                "parsed": parsed,
                "results": [],
                "total_found": 0,
                "search_metadata": {
                    "used_semantic_search": bool(parsed.get("cleaned_query")),
                    "applied_filters": self._get_applied_filters(parsed),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    # Always include any top-N candidates surfaced by the service layer,
                    # even if the final results are empty (zero-result analytics).
                    "observability_candidates": observability_candidates,
                    "cache_hit": False,
                },
            }
            # Cache empty results too (prevents repeated expensive queries)
            if cache_key and self.cache_service and not include_availability:
                self.cache_service.set(cache_key, empty_response, ttl=SEARCH_CACHE_TTL)
            return empty_response

        self._track_search_analytics(services[:limit])

        # Build response
        response: JsonDict = {
            "query": query,
            "parsed": parsed,
            "results": results[:limit],
            "total_found": len(results),
            "search_metadata": {
                "used_semantic_search": bool(parsed.get("cleaned_query")),
                "applied_filters": self._get_applied_filters(parsed),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "observability_candidates": observability_candidates,
                "cache_hit": False,
            },
        }

        # Cache the results (60-second TTL)
        if cache_key and self.cache_service and not include_availability:
            self.cache_service.set(cache_key, response, ttl=SEARCH_CACHE_TTL)
            logger.debug(f"Cached search results for query: {query[:30]}...")

        return response

    def _search_services(
        self, query_embedding: List[float], parsed: ParsedQuery, limit: int
    ) -> Tuple[JsonList, JsonList]:
        """Search for services using embeddings and filters, and prepare top-N candidates for observability."""

        # Lightweight helpers for fuzzy token matching (to capitalize on pg_trgm in exact-text phase)
        def _levenshtein_distance(a: str, b: str) -> int:
            if a == b:
                return 0
            la, lb = len(a), len(b)
            if la == 0:
                return lb
            if lb == 0:
                return la
            # DP row-wise (space-optimized)
            prev = list(range(lb + 1))
            curr = [0] * (lb + 1)
            for i in range(1, la + 1):
                curr[0] = i
                ca = a[i - 1]
                for j in range(1, lb + 1):
                    cb = b[j - 1]
                    cost = 0 if ca == cb else 1
                    curr[j] = min(
                        prev[j] + 1,  # deletion
                        curr[j - 1] + 1,  # insertion
                        prev[j - 1] + cost,  # substitution
                    )
                prev, curr = curr, prev
            return prev[lb]

        def _has_fuzzy_token_overlap(query_text: str, candidate_name: str) -> bool:
            q_tokens = [t for t in query_text.lower().split() if t]
            name_tokens = [t for t in candidate_name.lower().replace("-", " ").split() if t]
            if not q_tokens or not name_tokens:
                return False
            for qt in q_tokens:
                for nt in name_tokens:
                    # Allow small spelling errors: distance <= 1 for short tokens, <= 2 for length >= 6
                    dist = _levenshtein_distance(qt, nt)
                    if (len(qt) < 6 and dist <= 1) or (len(qt) >= 6 and dist <= 2):
                        return True
            return False

        cleaned_query_value = parsed.get("cleaned_query")
        cleaned_query_text = cleaned_query_value if isinstance(cleaned_query_value, str) else ""

        # Determine filters
        location_value = parsed.get("location")
        location_constraints: JsonDict = location_value if isinstance(location_value, dict) else {}
        online_capable: Optional[bool] = None
        if location_constraints.get("online"):
            online_capable = True
        elif location_constraints.get("in_person"):
            online_capable = False

        # Always initialize to avoid unbound variable errors in rare branches
        similar_services: List[Tuple[Any, float]] = []

        # Determine search strategy based on query type
        raw_candidates: List[Tuple[Any, Optional[float], str]] = []
        if parsed.get("is_category_query"):
            # For category queries, use lower threshold for broader results
            # Start at 0.5 and relax to 0.4 for better category breadth like 'dance'
            thresholds = [0.5, 0.4]
            similar_services = []
            for th in thresholds:
                similar_services = self.catalog_repository.find_similar_by_embedding(
                    embedding=query_embedding, limit=limit, threshold=th
                )
                if similar_services:
                    break

            # If a specific category was detected, restrict to that category
            category_name = parsed.get("category")
            if category_name and similar_services:
                filtered = []
                for svc, score in similar_services:
                    try:
                        if svc.category and svc.category.name.lower() == category_name.lower():
                            filtered.append((svc, score))
                    except Exception:
                        # If relationship not loaded, keep original entry
                        pass
                if filtered:
                    similar_services = filtered
        else:
            # For specific service queries, first try exact match; if none, fall back to semantic search
            exact_candidates: List[Tuple[Any, float]] = []  # (service, score)
            _performed_vector_search = False
            if cleaned_query_text:
                # Search for exact/close text matches
                exact_services = self.catalog_repository.search_services(
                    query_text=cleaned_query_text, limit=10
                )
                query_lower = cleaned_query_text.lower()
                q_tokens = [t for t in query_lower.split() if t]
                for service in exact_services:
                    service_name_lower = (service.name or "").lower()
                    score = 0.0
                    if service_name_lower == query_lower:
                        score = 1.0
                    elif query_lower in service_name_lower:
                        ratio = len(query_lower) / max(1, len(service_name_lower))
                        score = 0.85 + 0.1 * ratio  # 0.85..0.95
                    elif service_name_lower in query_lower:
                        score = 0.8
                    if any(tok in service_name_lower for tok in q_tokens):
                        score = max(score, 0.8)
                    # NEW: fuzzy token overlap (e.g., paino→piano, tenis→tennis)
                    if score < 0.8 and _has_fuzzy_token_overlap(query_lower, service_name_lower):
                        score = max(score, 0.82)
                    if score >= 0.8:
                        exact_candidates.append((service, score))

                if exact_candidates:
                    exact_candidates.sort(key=lambda x: x[1], reverse=True)
                    raw_candidates = [(svc, score, "exact") for svc, score in exact_candidates[:10]]
                    similar_services = exact_candidates[:5]

            # If no exact candidates were found, perform semantic search with tiered thresholds
            if not exact_candidates:
                thresholds = [0.7, 0.6, 0.5, 0.4]
                similar_services = []
                for th in thresholds:
                    similar_services = self.catalog_repository.find_similar_by_embedding(
                        embedding=query_embedding, limit=limit, threshold=th
                    )
                    if similar_services:
                        break
                _performed_vector_search = True
                if similar_services:
                    raw_candidates = [
                        (svc, score, "vector") for svc, score in similar_services[:10]
                    ]

        # Convert to service dicts with scores
        services: JsonList = []
        for service, score in similar_services or []:
            # Apply additional filters
            if online_capable is not None and service.online_capable != online_capable:
                continue

            service_dict = service.to_dict()
            service_dict["relevance_score"] = score

            # Get analytics
            analytics = self.analytics_repository.get_or_create(service.id)
            service_dict["demand_score"] = analytics.demand_score
            service_dict["is_trending"] = analytics.is_trending

            # Simple hybrid re-ranking features (tuning pass)
            token_bonus = 0.0
            if cleaned_query_text:
                q = cleaned_query_text.lower()
                name_l = str(service_dict.get("name", "")).lower()
                desc_l = (service_dict.get("description") or "").lower()
                tokens = [t for t in q.split() if t]
                if any(tok in name_l for tok in tokens):
                    token_bonus += 0.06  # slightly higher boost on name overlap
                if any(tok in desc_l for tok in tokens):
                    token_bonus += 0.025

                # Exact alias handling: if an exact search_terms match, give a meaningful bump
                search_terms_value = service_dict.get("search_terms")
                if isinstance(search_terms_value, (list, tuple)):
                    terms = [str(t).lower() for t in search_terms_value]
                else:
                    terms = []
                if terms and (q in terms or any(q == term for term in terms)):
                    token_bonus += 0.08
            service_dict["relevance_score"] = min(
                service_dict["relevance_score"] + token_bonus, 1.0
            )

            services.append(service_dict)

        # Apply dynamic relevance cutoff and token-overlap pruning for specific queries
        if not parsed.get("is_category_query") and services:
            # Determine a dynamic minimum based on the top score (slightly looser after pg_trgm)
            top_score = max(s.get("relevance_score", 0.0) for s in services)
            # Allow closely related neighbors (e.g., keyboard for piano), drop distant ones
            min_score = max(0.5, top_score * 0.68)

            q_tokens = [t for t in cleaned_query_text.lower().split() if len(t) > 2]

            def has_token_overlap(svc: JsonDict) -> bool:
                if not q_tokens:
                    return False
                name_l = (svc.get("name") or "").lower()
                desc_l = (svc.get("description") or "").lower()
                search_terms_value = svc.get("search_terms")
                if isinstance(search_terms_value, (list, tuple)):
                    terms = [str(t).lower() for t in search_terms_value]
                else:
                    terms = []
                if any(tok in name_l for tok in q_tokens):
                    return True
                if any(tok in desc_l for tok in q_tokens):
                    return True
                if terms and any(any(tok in term for tok in q_tokens) for term in terms):
                    return True
                return False

            pruned = [
                s
                for s in services
                if s.get("relevance_score", 0.0) >= min_score or has_token_overlap(s)
            ]

            # Keep up to 3 to allow one closely related neighbor (e.g., Keyboard) to appear
            services = pruned[:3]

        # Fallback for category queries: if nothing survived, pick active services from that category
        if parsed.get("is_category_query") and not services:
            try:
                category_name = parsed.get("category")
                if category_name:
                    # Get all active services with categories eagerly loaded, then filter
                    all_active = self.catalog_repository.get_active_services_with_categories()
                    fallback = []
                    for svc in all_active:
                        try:
                            if (
                                svc.category
                                and svc.category.name.lower() == category_name.lower()
                                and any(s.is_active for s in svc.instructor_services)
                            ):
                                svc_dict = svc.to_dict()
                                svc_dict["relevance_score"] = 0.51  # modest default
                                # Add analytics if available
                                analytics = self.analytics_repository.get_or_create(svc.id)
                                svc_dict["demand_score"] = analytics.demand_score
                                svc_dict["is_trending"] = analytics.is_trending
                                fallback.append(svc_dict)
                        except Exception:
                            continue
                    services = fallback[: limit or 10]
            except Exception:
                pass

        # Observability: when no services, log top-N vector candidates to aid tuning
        if not services:
            try:
                top_candidates = self.catalog_repository.find_similar_by_embedding(
                    embedding=query_embedding,
                    limit=10,
                    threshold=0.0,
                )
                if top_candidates:
                    # If we didn't already collect raw candidates above, promote these
                    # vector neighbors to raw candidates so the API can return
                    # observability_candidates for zero-result queries.
                    if not raw_candidates:
                        raw_candidates = [
                            (svc, score, "vector") for svc, score in top_candidates[:10]
                        ]
                    logger.info(
                        "NL Search observability: top vector candidates when no results",
                        extra={
                            "parsed": parsed,
                            "candidates": [
                                {"id": svc.id, "name": svc.name, "score": float(f"{score:.4f}")}
                                for svc, score in top_candidates
                            ],
                        },
                    )
                else:
                    logger.info(
                        "NL Search observability: no vector candidates found",
                        extra={"parsed": parsed},
                    )
            except Exception as e:
                logger.warning(f"Observability logging failed: {e}")

        # Build observability candidates list with hybrid scores
        def _token_bonus_for(service_name: str, service_desc: str) -> float:
            bonus = 0.0
            if parsed.get("cleaned_query"):
                q = parsed["cleaned_query"].lower()
                name_l = (service_name or "").lower()
                desc_l = (service_desc or "").lower()
                if any(tok in name_l for tok in q.split()):
                    bonus += 0.05
                if any(tok in desc_l for tok in q.split()):
                    bonus += 0.02
            return bonus

        obs: JsonList = []
        seen = set()
        for idx, (svc, base_score, source) in enumerate(raw_candidates[:10]):
            if svc.id in seen:
                continue
            seen.add(svc.id)
            # Compute hybrid score similar to main ranking
            bonus = _token_bonus_for(
                getattr(svc, "name", ""), getattr(svc, "description", "") or ""
            )
            hybrid_score = min((base_score or 0.0) + bonus, 1.0)
            obs.append(
                {
                    "position": idx + 1,
                    "service_catalog_id": svc.id,
                    "name": svc.name,
                    "score": hybrid_score,
                    "vector_score": base_score if source == "vector" else None,
                    "lexical_score": base_score if source == "exact" else None,
                    "source": "hybrid" if source == "vector" else source,
                }
            )

        return services, obs

    # TODO(part2): refine instructor matching typing & availability integration.
    def _find_instructors_for_services(
        self, services: JsonList, parsed: ParsedQuery, limit: int
    ) -> JsonList:
        """Find instructors offering the matched services.

        Optimized to use batch queries:
        1. Single query for all instructors across all services
        2. Single query for all service areas across all instructors
        This reduces N+1 queries from 26-40 to 2 per search.
        """
        if not services:
            return []

        results: JsonList = []
        price_value = parsed.get("price")
        price_constraints = price_value if isinstance(price_value, dict) else {}
        location_value = parsed.get("location")
        location_constraints = location_value if isinstance(location_value, dict) else {}
        level_value = parsed.get("level")
        level_constraints = level_value if isinstance(level_value, dict) else {}

        # Step 1: Collect all service IDs
        service_ids = [service["id"] for service in services]
        service_map = {service["id"]: service for service in services}

        # Step 2: Batch query - get all instructors for all services
        instructors_by_service = self.instructor_repository.find_by_service_ids(
            service_catalog_ids=service_ids,
            min_price=price_constraints.get("min"),
            max_price=price_constraints.get("max"),
            limit_per_service=limit,
        )

        # Step 3: Collect all unique instructor user IDs
        all_instructor_ids: set[str] = set()
        for profiles in instructors_by_service.values():
            for profile in profiles:
                all_instructor_ids.add(profile.user_id)

        # Step 4: Batch query - get all service areas at once
        service_areas_by_instructor = self.service_area_repository.list_for_instructors(
            list(all_instructor_ids)
        )

        # Step 5: Build results using pre-fetched data
        from ..schemas.search_responses import InstructorInfo

        for service_id, instructors in instructors_by_service.items():
            service = service_map.get(service_id)
            if not service:
                continue

            for instructor_profile in instructors:
                # Get the specific service offered by this instructor
                instructor_service = next(
                    (
                        s
                        for s in instructor_profile.instructor_services
                        if s.service_catalog_id == service_id and s.is_active
                    ),
                    None,
                )

                if not instructor_service:
                    continue

                # Build service area context from pre-fetched data (no DB query)
                instructor_areas = service_areas_by_instructor.get(instructor_profile.user_id, [])
                service_area_context, boroughs_lower = self._build_service_area_context_from_areas(
                    instructor_areas
                )

                # Check location constraints
                if location_constraints:
                    if not self._matches_location_constraints(
                        instructor_service,
                        instructor_profile,
                        location_constraints,
                        boroughs_lower,
                    ):
                        continue

                # Check level constraints
                if level_constraints:
                    if not self._matches_level_constraints(instructor_service, level_constraints):
                        continue

                # Build result with privacy protection
                result = {
                    "service": service,
                    "instructor": InstructorInfo.from_user(
                        user=instructor_profile.user,
                        bio=instructor_profile.bio,
                        years_experience=instructor_profile.years_experience,
                        service_area_summary=service_area_context["service_area_summary"],
                        service_area_boroughs=service_area_context["service_area_boroughs"],
                        service_area_neighborhoods=service_area_context[
                            "service_area_neighborhoods"
                        ],
                    ).model_dump(),
                    "offering": {
                        "id": instructor_service.id,
                        "hourly_rate": instructor_service.hourly_rate,
                        "experience_level": instructor_service.experience_level,
                        "description": instructor_service.description,
                        "duration_options": instructor_service.duration_options,
                        "equipment_required": instructor_service.equipment_required,
                        "levels_taught": instructor_service.levels_taught,
                        "age_groups": instructor_service.age_groups,
                        "location_types": instructor_service.location_types,
                        "max_distance_miles": instructor_service.max_distance_miles,
                    },
                    "match_score": self._calculate_match_score(
                        service["relevance_score"], instructor_service, parsed
                    ),
                }
                coverage_regions = service_area_context.get("coverage_regions")
                coverage_region_ids = service_area_context.get("coverage_region_ids")
                if coverage_regions:
                    result["coverage_regions"] = coverage_regions
                if coverage_region_ids:
                    result["coverage_region_ids"] = coverage_region_ids
                results.append(result)

        # Sort by match score
        results.sort(key=lambda x: x["match_score"], reverse=True)

        return results

    def _build_service_area_context(self, instructor_id: str) -> tuple[JsonDict, set[str]]:
        """Construct service area payload used by search consumers."""
        service_areas = self.service_area_repository.list_for_instructor(instructor_id)
        neighborhoods: list[dict[str, Any]] = []
        boroughs: set[str] = set()
        coverage_regions: list[dict[str, Any]] = []
        coverage_region_ids: list[str] = []

        for area in service_areas:
            region = getattr(area, "neighborhood", None)
            region_code: str | None = getattr(region, "region_code", None)
            region_name: str | None = getattr(region, "region_name", None)
            borough: str | None = getattr(region, "parent_region", None)
            region_meta = getattr(region, "region_metadata", None)

            if isinstance(region_meta, dict):
                region_code = (
                    region_code or region_meta.get("nta_code") or region_meta.get("ntacode")
                )
                region_name = region_name or region_meta.get("nta_name") or region_meta.get("name")
                meta_borough = region_meta.get("borough")
                if isinstance(meta_borough, str) and meta_borough:
                    borough = meta_borough

            if borough:
                boroughs.add(borough)

            neighborhoods.append(
                {
                    "neighborhood_id": area.neighborhood_id,
                    "ntacode": region_code,
                    "name": region_name,
                    "borough": borough,
                }
            )

            coverage_regions.append(
                {
                    "region_id": area.neighborhood_id,
                    "name": region_name,
                    "borough": borough,
                    "coverage_type": getattr(area, "coverage_type", None),
                }
            )
            if area.is_active:
                coverage_region_ids.append(area.neighborhood_id)

        sorted_boroughs = sorted(boroughs)
        if sorted_boroughs:
            if len(sorted_boroughs) <= 2:
                summary = ", ".join(sorted_boroughs)
            else:
                summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"
        else:
            summary = ""

        context: JsonDict = {
            "service_area_neighborhoods": neighborhoods,
            "service_area_boroughs": sorted_boroughs,
            "service_area_summary": summary,
        }
        if coverage_regions:
            context["coverage_regions"] = coverage_regions
        if coverage_region_ids:
            context["coverage_region_ids"] = coverage_region_ids

        return context, {borough.lower() for borough in sorted_boroughs}

    def _build_service_area_context_from_areas(
        self, service_areas: list[Any]
    ) -> tuple[JsonDict, set[str]]:
        """Build service area context from pre-fetched areas (no DB query)."""
        neighborhoods: list[dict[str, Any]] = []
        boroughs: set[str] = set()
        coverage_regions: list[dict[str, Any]] = []
        coverage_region_ids: list[str] = []

        for area in service_areas:
            region = getattr(area, "neighborhood", None)
            region_code: str | None = getattr(region, "region_code", None)
            region_name: str | None = getattr(region, "region_name", None)
            borough: str | None = getattr(region, "parent_region", None)
            region_meta = getattr(region, "region_metadata", None)

            if isinstance(region_meta, dict):
                region_code = (
                    region_code or region_meta.get("nta_code") or region_meta.get("ntacode")
                )
                region_name = region_name or region_meta.get("nta_name") or region_meta.get("name")
                meta_borough = region_meta.get("borough")
                if isinstance(meta_borough, str) and meta_borough:
                    borough = meta_borough

            if borough:
                boroughs.add(borough)

            neighborhoods.append(
                {
                    "neighborhood_id": area.neighborhood_id,
                    "ntacode": region_code,
                    "name": region_name,
                    "borough": borough,
                }
            )

            coverage_regions.append(
                {
                    "region_id": area.neighborhood_id,
                    "name": region_name,
                    "borough": borough,
                    "coverage_type": getattr(area, "coverage_type", None),
                }
            )
            if area.is_active:
                coverage_region_ids.append(area.neighborhood_id)

        sorted_boroughs = sorted(boroughs)
        if sorted_boroughs:
            if len(sorted_boroughs) <= 2:
                summary = ", ".join(sorted_boroughs)
            else:
                summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"
        else:
            summary = ""

        context: JsonDict = {
            "service_area_neighborhoods": neighborhoods,
            "service_area_boroughs": sorted_boroughs,
            "service_area_summary": summary,
        }
        if coverage_regions:
            context["coverage_regions"] = coverage_regions
        if coverage_region_ids:
            context["coverage_region_ids"] = coverage_region_ids

        return context, {borough.lower() for borough in sorted_boroughs}

    def _matches_location_constraints(
        self,
        instructor_service: Any,
        instructor_profile: Any,
        location_constraints: JsonDict,
        service_area_boroughs_lower: Optional[set[str]] = None,
    ) -> bool:
        """Check if instructor matches location constraints."""
        if location_constraints.get("online"):
            if (
                not instructor_service.location_types
                or "online" not in instructor_service.location_types
            ):
                return False

        if location_constraints.get("in_person"):
            if (
                not instructor_service.location_types
                or "in-person" not in instructor_service.location_types
            ):
                return False

            if service_area_boroughs_lower is None:
                _, service_area_boroughs_lower = self._build_service_area_context(
                    instructor_profile.user_id
                )

            borough_requirements = {
                "manhattan": "manhattan",
                "brooklyn": "brooklyn",
                "queens": "queens",
                "bronx": "bronx",
                "staten_island": "staten island",
            }

            for key, label in borough_requirements.items():
                if location_constraints.get(key) and label not in service_area_boroughs_lower:
                    return False

        return True

    def _matches_level_constraints(
        self, instructor_service: Any, level_constraints: JsonDict
    ) -> bool:
        """Check if instructor matches level constraints."""
        if not instructor_service.levels_taught:
            return True  # No levels specified means all levels

        levels_lower = [level.lower() for level in instructor_service.levels_taught]
        age_groups_lower = [age.lower() for age in (instructor_service.age_groups or [])]

        # Check specific levels
        if level_constraints.get("beginner") and "beginner" not in levels_lower:
            return False
        if level_constraints.get("intermediate") and "intermediate" not in levels_lower:
            return False
        if level_constraints.get("advanced") and "advanced" not in levels_lower:
            return False

        # Check academic levels
        if level_constraints.get("high_school") and "high school" not in levels_lower:
            return False
        if level_constraints.get("college") and "college" not in levels_lower:
            return False
        if level_constraints.get("ap") and "ap" not in levels_lower:
            return False

        # Check age groups
        if level_constraints.get("kids"):
            if not any(age in age_groups_lower for age in ["kids", "children", "5-12", "6-12"]):
                return False
        if level_constraints.get("adults"):
            if not any(age in age_groups_lower for age in ["adults", "18+", "adult"]):
                return False

        return True

    def _calculate_match_score(
        self, relevance_score: float, instructor_service: Any, parsed: ParsedQuery
    ) -> float:
        """Calculate overall match score for ranking.

        Incorporates semantic relevance and a cautious rating lower-bound (Beta posterior 5th percentile).
        """
        score = relevance_score * 100  # Base score from semantic similarity

        # Boost for exact price match
        price_value = parsed.get("price")
        price_constraints = price_value if isinstance(price_value, dict) else {}
        if price_constraints:
            price = instructor_service.hourly_rate
            if price_constraints.get("min") and price_constraints.get("max"):
                # Price is in range
                mid_range = (price_constraints["min"] + price_constraints["max"]) / 2
                price_diff = abs(price - mid_range) / mid_range
                score *= 1 - price_diff * 0.2  # Up to 20% penalty for price difference

        # Boost for experience level
        if instructor_service.experience_level == "expert":
            score *= 1.1
        elif instructor_service.experience_level == "intermediate":
            score *= 1.05

        # Boost for location type match
        if parsed["location"].get("online") and "online" in (
            instructor_service.location_types or []
        ):
            score *= 1.1

        # Add cautious rating signal (Beta lower-bound at 5th percentile) using 4-5★ as positive
        try:
            instructor_id = (
                getattr(instructor_service, "instructor_profile_id", None)
                or getattr(instructor_service, "instructor_id", None)
                or getattr(instructor_service, "instructor", None)
            )
            if instructor_id:
                ratings = self.review_service.get_instructor_ratings(str(instructor_id))
                total = int(ratings.get("overall", {}).get("total_reviews", 0))
                # Approximate positives as reviews >=4 if breakdown available; fallback to Bayesian mean
                bayes = float(ratings.get("overall", {}).get("rating", 0.0))
                # Map mean to Bernoulli p by assuming linear map: p ~= (bayes-3)/2 for 3..5 range (rough)
                p_mean = max(0.0, min(1.0, (bayes - 3.0) / 2.0))
                alpha0, beta0 = 9.0, 1.0
                alpha = alpha0 + p_mean * total
                beta = beta0 + (1.0 - p_mean) * total
                # 5th percentile of Beta via simple approximation (mean - 2*std for moderate n)
                import math

                mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0
                var = (
                    (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
                    if (alpha + beta) > 1
                    else 0.0
                )
                std = math.sqrt(var)
                lb = max(0.0, mean - 2.0 * std)
                # Weight into score (scaled 0..100) with modest influence
                score *= 1.0 + (lb * 0.08)  # up to +8% boost for strong lower-bound
        except Exception:
            pass

        return min(score, 100)  # Cap at 100

    def _filter_by_availability(self, results: JsonList, time_constraints: JsonDict) -> JsonList:
        """Filter results by instructor availability."""
        # This is a placeholder - actual implementation would check availability
        # For now, just return all results
        logger.info(f"Availability filtering requested for: {time_constraints}")
        return results

    def _track_search_analytics(self, services: JsonList) -> None:
        """Track search analytics for services."""
        for service in services:
            try:
                self.analytics_repository.increment_search_count(service["id"])
            except Exception as e:
                logger.error(f"Failed to track analytics for service {service['id']}: {e}")

    def _get_applied_filters(self, parsed: ParsedQuery) -> List[str]:
        """Get list of filters that were applied."""
        filters: List[str] = []

        price_value = parsed.get("price")
        price_constraints: JsonDict = price_value if isinstance(price_value, dict) else {}
        if price_constraints:
            if price_constraints.get("min") and price_constraints.get("max"):
                filters.append(f"price: ${price_constraints['min']}-${price_constraints['max']}")
            elif price_constraints.get("min"):
                filters.append(f"price: >${price_constraints['min']}")
            elif price_constraints.get("max"):
                filters.append(f"price: <${price_constraints['max']}")

        time_value = parsed.get("time")
        time_constraints: JsonDict = time_value if isinstance(time_value, dict) else {}
        if time_constraints:
            filters.extend([k for k, v in time_constraints.items() if v])

        location_value = parsed.get("location")
        location_constraints = location_value if isinstance(location_value, dict) else {}
        if location_constraints:
            filters.extend([k for k, v in location_constraints.items() if v])

        level_value = parsed.get("level")
        level_constraints = level_value if isinstance(level_value, dict) else {}
        if level_constraints:
            filters.extend([k for k, v in level_constraints.items() if v])

        return filters

    @BaseService.measure_operation("get_search_suggestions")
    def get_suggestions(self, partial_query: str) -> List[str]:
        """
        Get search suggestions based on partial query.

        Args:
            partial_query: Partial search query

        Returns:
            List of suggested queries
        """
        suggestions: List[str] = []

        # Get popular services matching the partial query
        services = self.catalog_repository.search_services(query_text=partial_query, limit=5)

        for service in services:
            # Basic suggestion
            suggestions.append(service.name.lower())

            # Suggestion with price
            min_price = getattr(service, "min_recommended_price", None)
            max_price = getattr(service, "max_recommended_price", None)
            if min_price is not None and max_price is not None:
                suggestions.append(f"{service.name.lower()} under ${max_price}")

            # Suggestion with online
            if service.online_capable:
                suggestions.append(f"online {service.name.lower()}")

        # Add time-based suggestions
        if not any(word in partial_query.lower() for word in ["today", "tomorrow", "week"]):
            if suggestions:
                suggestions.append(f"{suggestions[0]} today")
                suggestions.append(f"{suggestions[0]} this week")

        return list(set(suggestions))[:10]  # Unique suggestions, max 10


# Dependency injection
def get_search_service(db: Session) -> SearchService:
    """Get search service instance for dependency injection."""
    return SearchService(db)
