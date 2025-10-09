#!/usr/bin/env python3
"""Export region boundaries from database to GeoJSON cache file.

This script exports region boundaries from the database to a local GeoJSON file,
useful for creating or refreshing the cache from a known-good database.
"""

import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text

# Import settings
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings
from app.utils.env_logging import log_info

CACHE_DIR = Path(__file__).parent / "data"
CACHE_FILE = CACHE_DIR / "nyc_boundaries.geojson"


def export_boundaries():
    """Export region boundaries from database to GeoJSON cache."""
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        # Check if table exists and has data
        count = conn.execute(text("SELECT COUNT(*) FROM region_boundaries")).scalar()

        if count == 0:
            print("❌ No boundaries found in database")
            return False

        print(f"Found {count} boundaries in database")

        # Export as GeoJSON
        result = conn.execute(
            text(
                """
            SELECT
                region_code,
                region_name,
                parent_region,
                region_type,
                ST_AsGeoJSON(boundary) as geom_json,
                region_metadata
            FROM region_boundaries
            ORDER BY region_code
        """
            )
        )

        features = []
        for row in result:
            # Create feature with properties matching what the loader expects
            properties = {
                "ntacode": row.region_code,
                "ntaname": row.region_name,
                "boroname": row.parent_region,
            }

            # Add any metadata fields
            if row.region_metadata:
                properties.update(row.region_metadata)

            feature = {"type": "Feature", "properties": properties, "geometry": json.loads(row.geom_json)}
            features.append(feature)

        # Create GeoJSON FeatureCollection
        geojson = {"type": "FeatureCollection", "features": features}

        # Ensure cache directory exists
        CACHE_DIR.mkdir(exist_ok=True)

        # Save to cache file
        with open(CACHE_FILE, "w") as f:
            json.dump(geojson, f, indent=2)

        print(f"✅ Exported {len(features)} boundaries to {CACHE_FILE}")

        # Show file size
        size_mb = CACHE_FILE.stat().st_size / (1024 * 1024)
        print(f"📦 Cache file size: {size_mb:.1f} MB")

        return True


if __name__ == "__main__":
    site_mode = os.getenv("SITE_MODE", "").lower()
    if site_mode in {"local", "stg", "staging"}:
        log_info("stg", "Exporting from Staging database")
    elif "instainstru_test" in str(settings.database_url):
        log_info("int", "Exporting from Integration Test database")
    else:
        log_info("prod", "Exporting from production database - be careful!")

    success = export_boundaries()
    sys.exit(0 if success else 1)
