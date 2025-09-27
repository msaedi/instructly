#!/usr/bin/env python3
"""Download and cache NYC region boundaries.

This script downloads NYC NTA boundaries from NYC Open Data and saves them
locally as a GeoJSON file. This avoids repeated downloads and provides
resilience against API changes or downtime.
"""

import json
from pathlib import Path
import sys

import requests

# Output path for cached boundaries
CACHE_DIR = Path(__file__).parent / "data"
CACHE_FILE = CACHE_DIR / "nyc_boundaries.geojson"

# NYC Open Data endpoint that still works
NYC_DATA_URL = "https://data.cityofnewyork.us/resource/9nt8-h7nd.json"


def download_nyc_boundaries():
    """Download NYC NTA boundaries and save as GeoJSON."""
    print(f"Downloading NYC boundaries from {NYC_DATA_URL}...")

    try:
        response = requests.get(NYC_DATA_URL, timeout=60)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list) or not data:
            raise ValueError("Unexpected data format from NYC Open Data")

        print(f"Downloaded {len(data)} regions")

        # Convert to GeoJSON format
        features = []
        for item in data:
            if "the_geom" not in item:
                continue

            # Extract properties we need
            properties = {
                "ntacode": item.get("ntacode", ""),
                "ntaname": item.get("ntaname", ""),
                "boroname": item.get("boroname", ""),
                "borocode": item.get("borocode", ""),
                "cdta": item.get("cdta", ""),
            }

            # Create GeoJSON feature
            feature = {"type": "Feature", "properties": properties, "geometry": item["the_geom"]}
            features.append(feature)

        # Create GeoJSON FeatureCollection
        geojson = {"type": "FeatureCollection", "features": features}

        # Ensure cache directory exists
        CACHE_DIR.mkdir(exist_ok=True)

        # Save to file
        with open(CACHE_FILE, "w") as f:
            json.dump(geojson, f, indent=2)

        print(f"✅ Saved {len(features)} regions to {CACHE_FILE}")
        return True

    except Exception as e:
        print(f"❌ Error downloading boundaries: {e}")
        return False


if __name__ == "__main__":
    success = download_nyc_boundaries()
    sys.exit(0 if success else 1)
