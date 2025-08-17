"""Location enrichment service.

Adds region-specific metadata for addresses in a globally scalable way.

Scaffold: basic region detection (NYC bbox) and NYC enrichment via PostGIS
ST_Contains against the `nyc_neighborhoods` table when available. Falls back
to generic metadata if enrichment is unavailable or no match is found.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, TypedDict

from sqlalchemy.orm import Session

from ..repositories.region_boundary_repository import RegionBoundaryRepository


class EnrichmentResult(TypedDict, total=False):
    district: Optional[str]
    neighborhood: Optional[str]
    subneighborhood: Optional[str]
    location_metadata: dict


@dataclass
class LocationEnrichmentService:
    db: Session

    def _repo(self) -> RegionBoundaryRepository:
        return RegionBoundaryRepository(self.db)

    def detect_region(self, lat: float, lng: float) -> Optional[str]:
        """Very lightweight region detection by bounding boxes.

        Returns a region code like 'nyc' if coordinates fall within the region.
        """
        # NYC approximate bbox
        if 40.30 <= lat <= 41.10 and -74.30 <= lng <= -73.50:
            return "nyc"
        return None

    def enrich(self, lat: float, lng: float) -> EnrichmentResult:
        region = self.detect_region(lat, lng)
        if region == "nyc":
            repo = self._repo()
            if not repo.has_postgis():
                return EnrichmentResult(location_metadata={"region_type": "nyc"})
            return self._enrich_nyc(lat, lng)
        # Default generic
        return EnrichmentResult(location_metadata={"region_type": "generic"})

    def _enrich_nyc(self, lat: float, lng: float) -> EnrichmentResult:
        """NYC-specific enrichment: lookup NTA (neighborhood) via PostGIS.

        Reads from `nyc_neighborhoods` polygon table. If not available, falls back.
        """
        # Prefer generic region_boundaries via repository helper
        repo = self._repo()
        row = repo.find_region_by_point(lat, lng, region_type="nyc")

        if row:
            borough = row.get("parent_region")
            ntacode = row.get("region_code")
            ntaname = row.get("region_name")
            meta = row.get("region_metadata") or {}
            community_district = meta.get("community_district")
            return EnrichmentResult(
                district=borough,
                neighborhood=ntaname,
                location_metadata={
                    "country": "US",
                    "region_type": "nyc",
                    "nyc": {
                        "borough": borough,
                        "nta_code": ntacode,
                        "nta_name": ntaname,
                        "community_district": community_district,
                    },
                },
            )

        # Skip legacy fallback here to keep service repository-driven; default to metadata-only
        row2 = None

        if row2:
            borough = row2.get("borough")
            ntacode = row2.get("ntacode")
            ntaname = row2.get("ntaname")
            community_district = row2.get("community_district")
            return EnrichmentResult(
                district=borough,
                neighborhood=ntaname,
                location_metadata={
                    "country": "US",
                    "region_type": "nyc",
                    "nyc": {
                        "borough": borough,
                        "nta_code": ntacode,
                        "nta_name": ntaname,
                        "community_district": community_district,
                    },
                },
            )

        # No match: still label as NYC region
        return EnrichmentResult(location_metadata={"region_type": "nyc"})
