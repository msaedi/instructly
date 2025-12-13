# backend/app/repositories/nl_search_repository.py
"""
Repository for NL Search reference data.

Provides access to locations and price thresholds for the query parser.
"""

from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.nl_search import NYCLocation, PriceThreshold
from app.repositories.base_repository import BaseRepository


class NYCLocationRepository(BaseRepository[NYCLocation]):
    """Repository for NYC location lookups."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, NYCLocation)

    def get_all_with_aliases(self) -> List[NYCLocation]:
        """
        Get all NYC locations with their aliases.

        Returns:
            List of all NYCLocation records for caching.
        """
        return self.get_all(limit=1000)  # Reasonable limit for location data

    def build_location_cache(self) -> Dict[str, Dict[str, str]]:
        """
        Build a lookup cache mapping location names/aliases to their info.

        Returns:
            Dict mapping lowercase name/alias to location info dict.
        """
        cache: Dict[str, Dict[str, str]] = {}
        locations = self.get_all_with_aliases()

        for loc in locations:
            # Add main name
            cache[loc.name.lower()] = {
                "name": loc.name,
                "type": loc.type,
                "borough": loc.borough,
            }
            # Add aliases
            if loc.aliases:
                for alias in loc.aliases:
                    cache[alias.lower()] = {
                        "name": loc.name,
                        "type": loc.type,
                        "borough": loc.borough,
                    }

        return cache


class PriceThresholdRepository(BaseRepository[PriceThreshold]):
    """Repository for price threshold lookups."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, PriceThreshold)

    def get_all_thresholds(self) -> List[PriceThreshold]:
        """
        Get all price thresholds.

        Returns:
            List of all PriceThreshold records for caching.
        """
        return self.get_all(limit=100)  # Reasonable limit for threshold data

    def build_threshold_cache(self) -> Dict[Tuple[str, str], int]:
        """
        Build a lookup cache mapping (category, intent) to max_price.

        Returns:
            Dict mapping (category, intent) tuple to max_price.
        """
        cache: Dict[Tuple[str, str], int] = {}
        thresholds = self.get_all_thresholds()

        for t in thresholds:
            cache[(t.category, t.intent)] = t.max_price

        return cache
