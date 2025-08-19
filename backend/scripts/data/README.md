# Region Boundaries Cache

This directory contains cached NYC region boundary data.

## Why Cache?

1. **NYC Open Data API instability**: Many endpoints have broken or changed (404/500 errors as of Aug 2025)
   - `.geojson` endpoints return 500 errors
   - Geospatial API endpoints return 404 errors
   - Only `.json` endpoint still works
2. **Data rarely changes**: NYC NTA boundaries only update with census (~10 years)
3. **Performance**: Avoids repeated downloads during development
4. **Reliability**: Tests can run even when NYC Open Data is down

## Current Data

- **File**: `nyc_boundaries.geojson` (in .gitignore)
- **Source**: NYC Neighborhood Tabulation Areas (NTAs) 2020
- **Regions**: 262 NYC neighborhoods
- **Size**: ~700KB (simplified geometries from database export)
- **Last Update**: 2020 census (next update expected ~2030)

## How the Cache Works

1. **Automatic cache check**: `load_region_boundaries.py` checks for cache first
2. **Age warning**: Warns if cache is >365 days old (but still uses it)
3. **Fallback to download**: Only downloads if cache missing or forced
4. **Auto-save**: Successful downloads automatically create/update cache

## How to Refresh Cache

### When NYC releases new boundaries (e.g., 2030 census):

#### Option 1: Force refresh from NYC Open Data
```bash
# Force download even if cache exists
python scripts/load_region_boundaries.py --force-refresh
```

#### Option 2: Export from a good database
```bash
# If STG has the latest data
USE_STG_DATABASE=true python scripts/export_boundaries.py

# Or from INT if that's updated
python scripts/export_boundaries.py
```

#### Option 3: Manual download and load
```bash
# Download fresh data (creates cache automatically)
python scripts/download_nyc_boundaries.py

# Then load into database
python scripts/load_region_boundaries.py
```

## How It Works

1. `load_region_boundaries.py` checks for `nyc_boundaries.geojson` first
2. If found, uses cached data (avoids download)
3. If not found, attempts download from NYC Open Data
4. Falls back through multiple URLs if primary fails

## Notes

- The cache file is in `.gitignore` (don't commit)
- For CI/CD, consider storing in S3 or artifact storage
- The INT database doesn't require boundaries for tests to pass
