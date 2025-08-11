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

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List

from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from ..repositories.factory import RepositoryFactory
from .base import BaseService

logger = logging.getLogger(__name__)

# Module-level model cache to avoid reloading on every request
_model_cache = {}


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
        r"\binstructors?\b$",  # Generic "instructors" at end
        r"\bteachers?\b$",  # Generic "teachers" at end
    ]

    def parse(self, query: str) -> Dict:
        """
        Parse a natural language query.

        Args:
            query: Natural language search query

        Returns:
            Dictionary with extracted constraints and cleaned query
        """
        query_lower = query.lower()
        constraints = {
            "original_query": query,
            "cleaned_query": query,
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
                    constraints["price"][constraint_type.replace("_price", "")] = float(match.group(1))

                # Remove price from cleaned query
                constraints["cleaned_query"] = re.sub(pattern, "", constraints["cleaned_query"])

        # Extract time constraints
        for pattern, time_type in self.TIME_PATTERNS:
            if re.search(pattern, query_lower):
                constraints["time"][time_type] = True
                constraints["cleaned_query"] = re.sub(pattern, "", constraints["cleaned_query"])

        # Extract location constraints
        for pattern, location_type in self.LOCATION_PATTERNS:
            if re.search(pattern, query_lower):
                constraints["location"][location_type] = True
                constraints["cleaned_query"] = re.sub(pattern, "", constraints["cleaned_query"])

        # Extract level constraints
        for pattern, level_type in self.LEVEL_PATTERNS:
            if re.search(pattern, query_lower):
                constraints["level"][level_type] = True
                constraints["cleaned_query"] = re.sub(pattern, "", constraints["cleaned_query"])

        # Clean up the query
        constraints["cleaned_query"] = " ".join(constraints["cleaned_query"].split())

        # Normalize service names
        cleaned_lower = constraints["cleaned_query"].lower()
        for alias, canonical in self.SERVICE_ALIASES.items():
            # Use word boundaries to avoid partial replacements
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, cleaned_lower):
                constraints["cleaned_query"] = re.sub(
                    pattern, canonical.lower(), constraints["cleaned_query"], flags=re.IGNORECASE
                )
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

    def __init__(self, db: Session, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize search service.

        Args:
            db: Database session
            model_name: Sentence transformer model to use
        """
        super().__init__(db)

        # Initialize components
        self.parser = QueryParser()
        self._model_name = model_name
        # Get cached model - loads once, reuses across requests
        self.model = get_cached_model(model_name)

        # Initialize repositories
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)
        self.analytics_repository = RepositoryFactory.create_service_analytics_repository(db)
        self.instructor_repository = RepositoryFactory.create_instructor_profile_repository(db)

    @BaseService.measure_operation("natural_language_search")
    def search(self, query: str, limit: int = 20, include_availability: bool = False) -> Dict:
        """
        Perform natural language search.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            include_availability: Whether to check instructor availability

        Returns:
            Search results with services, instructors, and metadata
        """
        # Parse the query
        parsed = self.parser.parse(query)
        logger.info(f"Parsed query: {parsed}")

        # Generate embedding for cleaned query
        if parsed["cleaned_query"]:
            query_embedding = self.model.encode([parsed["cleaned_query"]])[0].tolist()
        else:
            # If no service query remains, use full query
            query_embedding = self.model.encode([query])[0].tolist()

        # Search for services using semantic similarity
        services = self._search_services(
            query_embedding=query_embedding, parsed=parsed, limit=limit * 2  # Get more to filter later
        )

        # Find instructors for matched services
        results = self._find_instructors_for_services(services=services, parsed=parsed, limit=limit)

        # Check availability if requested
        if include_availability and parsed.get("time"):
            results = self._filter_by_availability(results, parsed["time"])

        # Track search analytics
        self._track_search_analytics(services[:limit])

        # Build response
        return {
            "query": query,
            "parsed": parsed,
            "results": results[:limit],
            "total_found": len(results),
            "search_metadata": {
                "used_semantic_search": bool(parsed["cleaned_query"]),
                "applied_filters": self._get_applied_filters(parsed),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _search_services(self, query_embedding: List[float], parsed: Dict, limit: int) -> List[Dict]:
        """Search for services using embeddings and filters."""
        # Determine filters
        online_capable = None
        if parsed["location"].get("online"):
            online_capable = True
        elif parsed["location"].get("in_person"):
            online_capable = False

        # Determine search strategy based on query type
        if parsed.get("is_category_query"):
            # For category queries, use lower threshold for broader results
            similar_services = self.catalog_repository.find_similar_by_embedding(
                embedding=query_embedding, limit=limit, threshold=0.3
            )
        else:
            # For specific service queries, first try exact match
            exact_match_service = None
            if parsed["cleaned_query"]:
                # Search for exact service name match
                exact_services = self.catalog_repository.search_services(
                    query_text=parsed["cleaned_query"], limit=5  # Get top 5 to check for exact matches
                )
                # Look for exact or very close matches
                for service in exact_services:
                    service_name_lower = service.name.lower()
                    query_lower = parsed["cleaned_query"].lower()
                    # Check for exact match or if the service name is in the query
                    # This handles "guitar lessons" matching "guitar"
                    if (
                        service_name_lower == query_lower
                        or query_lower in service_name_lower
                        or service_name_lower in query_lower
                    ):
                        exact_match_service = service
                        break

            # If we found an exact match, use only that service
            if exact_match_service:
                similar_services = [(exact_match_service, 1.0)]  # Perfect score for exact match
            else:
                # Otherwise, do semantic search with higher threshold for precision
                similar_services = self.catalog_repository.find_similar_by_embedding(
                    embedding=query_embedding, limit=limit, threshold=0.7  # High threshold for specific searches
                )

        # Convert to service dicts with scores
        services = []
        for service, score in similar_services:
            # Apply additional filters
            if online_capable is not None and service.online_capable != online_capable:
                continue

            service_dict = service.to_dict()
            service_dict["relevance_score"] = score

            # Get analytics
            analytics = self.analytics_repository.get_or_create(service.id)
            service_dict["demand_score"] = analytics.demand_score
            service_dict["is_trending"] = analytics.is_trending

            services.append(service_dict)

        return services

    def _find_instructors_for_services(self, services: List[Dict], parsed: Dict, limit: int) -> List[Dict]:
        """Find instructors offering the matched services."""
        results = []

        for service in services:
            # Get instructors for this service with filters
            instructors = self.instructor_repository.find_by_filters(
                service_catalog_id=service["id"],
                min_price=parsed["price"].get("min"),
                max_price=parsed["price"].get("max"),
                limit=limit,
            )

            for instructor_profile in instructors:
                # Get the specific service offered by this instructor
                instructor_service = next(
                    (
                        s
                        for s in instructor_profile.instructor_services
                        if s.service_catalog_id == service["id"] and s.is_active
                    ),
                    None,
                )

                if not instructor_service:
                    continue

                # Check location constraints
                if parsed["location"]:
                    if not self._matches_location_constraints(
                        instructor_service, instructor_profile, parsed["location"]
                    ):
                        continue

                # Check level constraints
                if parsed["level"]:
                    if not self._matches_level_constraints(instructor_service, parsed["level"]):
                        continue

                # Build result
                result = {
                    "service": service,
                    "instructor": {
                        "id": instructor_profile.user_id,
                        "first_name": instructor_profile.user.first_name,
                        "last_name": instructor_profile.user.last_name,
                        "bio": instructor_profile.bio,
                        "years_experience": instructor_profile.years_experience,
                        "areas_of_service": instructor_profile.areas_of_service,
                    },
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
                    "match_score": self._calculate_match_score(service["relevance_score"], instructor_service, parsed),
                }

                results.append(result)

        # Sort by match score
        results.sort(key=lambda x: x["match_score"], reverse=True)

        return results

    def _matches_location_constraints(self, instructor_service, instructor_profile, location_constraints: Dict) -> bool:
        """Check if instructor matches location constraints."""
        if location_constraints.get("online"):
            if not instructor_service.location_types or "online" not in instructor_service.location_types:
                return False

        if location_constraints.get("in_person"):
            if not instructor_service.location_types or "in-person" not in instructor_service.location_types:
                return False

            # Check specific boroughs
            areas = instructor_profile.areas_of_service.lower() if instructor_profile.areas_of_service else ""
            for borough in ["manhattan", "brooklyn", "queens", "bronx", "staten_island"]:
                if location_constraints.get(borough) and borough.replace("_", " ") not in areas:
                    return False

        return True

    def _matches_level_constraints(self, instructor_service, level_constraints: Dict) -> bool:
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

    def _calculate_match_score(self, relevance_score: float, instructor_service, parsed: Dict) -> float:
        """Calculate overall match score for ranking."""
        score = relevance_score * 100  # Base score from semantic similarity

        # Boost for exact price match
        if parsed["price"]:
            price = instructor_service.hourly_rate
            if parsed["price"].get("min") and parsed["price"].get("max"):
                # Price is in range
                mid_range = (parsed["price"]["min"] + parsed["price"]["max"]) / 2
                price_diff = abs(price - mid_range) / mid_range
                score *= 1 - price_diff * 0.2  # Up to 20% penalty for price difference

        # Boost for experience level
        if instructor_service.experience_level == "expert":
            score *= 1.1
        elif instructor_service.experience_level == "intermediate":
            score *= 1.05

        # Boost for location type match
        if parsed["location"].get("online") and "online" in (instructor_service.location_types or []):
            score *= 1.1

        return min(score, 100)  # Cap at 100

    def _filter_by_availability(self, results: List[Dict], time_constraints: Dict) -> List[Dict]:
        """Filter results by instructor availability."""
        # This is a placeholder - actual implementation would check availability
        # For now, just return all results
        logger.info(f"Availability filtering requested for: {time_constraints}")
        return results

    def _track_search_analytics(self, services: List[Dict]) -> None:
        """Track search analytics for services."""
        for service in services:
            try:
                self.analytics_repository.increment_search_count(service["id"])
            except Exception as e:
                logger.error(f"Failed to track analytics for service {service['id']}: {e}")

    def _get_applied_filters(self, parsed: Dict) -> List[str]:
        """Get list of filters that were applied."""
        filters = []

        if parsed["price"]:
            if parsed["price"].get("min") and parsed["price"].get("max"):
                filters.append(f"price: ${parsed['price']['min']}-${parsed['price']['max']}")
            elif parsed["price"].get("min"):
                filters.append(f"price: >${parsed['price']['min']}")
            elif parsed["price"].get("max"):
                filters.append(f"price: <${parsed['price']['max']}")

        if parsed["time"]:
            filters.extend([k for k, v in parsed["time"].items() if v])

        if parsed["location"]:
            filters.extend([k for k, v in parsed["location"].items() if v])

        if parsed["level"]:
            filters.extend([k for k, v in parsed["level"].items() if v])

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
        suggestions = []

        # Get popular services matching the partial query
        services = self.catalog_repository.search_services(query_text=partial_query, limit=5)

        for service in services:
            # Basic suggestion
            suggestions.append(service.name.lower())

            # Suggestion with price
            if service.min_recommended_price:
                suggestions.append(f"{service.name.lower()} under ${service.max_recommended_price}")

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
