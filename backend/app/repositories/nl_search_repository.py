# backend/app/repositories/nl_search_repository.py
"""
Repository for NL Search reference data.

Provides access to locations and price thresholds for the query parser.
Supports multi-region architecture for scalability beyond NYC.
"""

from typing import Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from app.models.nl_search import PriceThreshold, RegionSettings, SearchLocation
from app.repositories.base_repository import BaseRepository


class SearchLocationRepository(BaseRepository[SearchLocation]):
    """Repository for search location lookups with multi-region support."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, SearchLocation)

    def get_all_with_aliases(self, region_code: str = "nyc") -> List[SearchLocation]:
        """
        Get all locations for a specific region with their aliases.

        Args:
            region_code: Region to filter by (default: nyc)

        Returns:
            List of SearchLocation records for caching.
        """
        result = (
            self.db.query(SearchLocation)
            .filter(
                SearchLocation.region_code == region_code,
                SearchLocation.is_active == True,  # noqa: E712
            )
            .limit(1000)
            .all()
        )
        return cast(List[SearchLocation], result)

    def build_location_cache(self, region_code: str = "nyc") -> Dict[str, Dict[str, Optional[str]]]:
        """
        Build a lookup cache mapping location names/aliases to their info.

        Args:
            region_code: Region to build cache for (default: nyc)

        Returns:
            Dict mapping lowercase name/alias to location info dict.
        """
        cache: Dict[str, Dict[str, Optional[str]]] = {}
        locations = self.get_all_with_aliases(region_code)

        for loc in locations:
            info = {
                "name": loc.name,
                "type": loc.type,
                "parent_name": loc.parent_name or loc.borough,  # Prefer parent_name
                "borough": loc.borough,  # Keep for backward compat
                "region_code": loc.region_code,
            }
            # Add main name
            cache[loc.name.lower()] = info
            # Add aliases
            if loc.aliases:
                for alias in loc.aliases:
                    cache[alias.lower()] = info

        return cache


# Backward compatibility alias
NYCLocationRepository = SearchLocationRepository


class PriceThresholdRepository(BaseRepository[PriceThreshold]):
    """Repository for price threshold lookups with multi-region support."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, PriceThreshold)

    def get_all_thresholds(self, region_code: Optional[str] = None) -> List[PriceThreshold]:
        """
        Get all price thresholds, optionally filtered by region.

        Args:
            region_code: Region to filter by (None = all regions)

        Returns:
            List of PriceThreshold records for caching.
        """
        query = self.db.query(PriceThreshold)
        if region_code:
            query = query.filter(PriceThreshold.region_code == region_code)
        result = query.limit(200).all()
        return cast(List[PriceThreshold], result)

    def build_threshold_cache(
        self, region_code: str = "nyc"
    ) -> Dict[Tuple[str, str], Dict[str, Optional[int]]]:
        """
        Build a lookup cache mapping (category, intent) to price info.

        Falls back to 'global' region if specific region threshold not found.

        Args:
            region_code: Region to build cache for (default: nyc)

        Returns:
            Dict mapping (category, intent) tuple to price info dict.
        """
        cache: Dict[Tuple[str, str], Dict[str, Optional[int]]] = {}

        # First load global fallback thresholds
        global_thresholds = self.get_all_thresholds(region_code="global")
        for t in global_thresholds:
            cache[(t.category, t.intent)] = {
                "max_price": t.max_price,
                "min_price": t.min_price,
            }

        # Then overlay region-specific thresholds
        if region_code != "global":
            region_thresholds = self.get_all_thresholds(region_code=region_code)
            for t in region_thresholds:
                cache[(t.category, t.intent)] = {
                    "max_price": t.max_price,
                    "min_price": t.min_price,
                }

        return cache


class RegionSettingsRepository(BaseRepository[RegionSettings]):
    """Repository for region settings lookups."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, RegionSettings)

    def get_by_region_code(self, region_code: str) -> Optional[RegionSettings]:
        """
        Get settings for a specific region.

        Args:
            region_code: Region identifier (e.g., 'nyc', 'chicago')

        Returns:
            RegionSettings or None if not found.
        """
        result = (
            self.db.query(RegionSettings).filter(RegionSettings.region_code == region_code).first()
        )
        return cast(Optional[RegionSettings], result)

    def get_active_regions(self) -> List[RegionSettings]:
        """
        Get all active regions.

        Returns:
            List of active RegionSettings.
        """
        result = (
            self.db.query(RegionSettings)
            .filter(RegionSettings.is_active == True)  # noqa: E712
            .all()
        )
        return cast(List[RegionSettings], result)
