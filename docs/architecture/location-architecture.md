### Location Architecture: Addresses, Enrichment, and Region Boundaries

This document describes the location system implemented across the backend and frontend. It replaces NYC‑specific columns with a flexible, provider‑agnostic architecture suitable for multiple cities/regions.

### Goals
- Generic address storage for users (multiple addresses, default flag, soft delete)
- Provider‑agnostic geocoding (Google, Mapbox, or mock) with a consistent data model
- Region enrichment from polygons (e.g., borough/district/neighborhood) using a single global table
- Repository pattern throughout; no direct SQL in services

### Core Data Structures
- `user_addresses`
  - Generic fields: `street_line1`, `street_line2`, `locality` (city), `administrative_area` (state), `postal_code`, `country_code`
  - Coordinates: `latitude`, `longitude`
  - Provider: `place_id`, `verification_status`, `normalized_payload` (JSON)
  - Generic enrichment fields: `district`, `neighborhood`, `subneighborhood`, `location_metadata` (JSON)
  - Defaults/soft delete: `is_default`, `is_active`

- `region_boundaries`
  - `region_type` (e.g., `nyc`), `region_code`, `region_name`, `parent_region`
  - Spatial columns: `boundary` (POLYGON, SRID 4326), `centroid` (POINT)
  - `region_metadata` (JSON) captures region‑specific attributes (e.g., NYC community district)

- `instructor_service_areas`
  - References `region_boundaries.id` (generic), not NYC‑specific tables

### Services and Repositories
- `RegionBoundaryRepository`
  - `has_postgis()`: checks for PostGIS availability
  - `find_region_by_point(lat, lng, region_type)`: returns the first boundary intersecting a point
  - Also includes a WKT insert helper used in tests

- `LocationEnrichmentService`
  - Detects region by bbox (e.g., NYC)
  - Uses `RegionBoundaryRepository` (repository pattern) to enrich an address from polygons
  - Returns a normalized dict with `district`, `neighborhood`, and `location_metadata`

- `AddressService`
  - `create_address` / `update_address`:
    - Resolves `place_id` via provider and fills core fields
    - Normalizes `country_code` to ISO‑3166 alpha‑2 (e.g., `US`)
    - Defaults `recipient_name` to the user’s full name when not provided
    - Calls `LocationEnrichmentService` when `latitude`/`longitude` are present
  - `delete_address`: soft delete

### Geocoding Providers (Provider‑Agnostic)
- `GoogleMapsProvider`, `MapboxProvider`, `MockProvider` implement `GeocodingProvider`
  - All return a consistent `GeocodedAddress` with city/state/postal/country
  - Providers normalize or are normalized to ISO‑3166 alpha‑2 country codes

Environment variables:
- `GEOCODING_PROVIDER` = `google` | `mapbox` | `mock`
- `GOOGLE_MAPS_API_KEY`
- `MAPBOX_ACCESS_TOKEN`

### API Endpoints
- `GET /api/addresses/me` – list current user’s addresses
- `POST /api/addresses/me` – create address (enriches if coords available)
- `PATCH /api/addresses/me/{id}` – update address (re‑enrich if needed)
- `DELETE /api/addresses/me/{id}` – soft delete (returns typed `DeleteResponse`)
- `GET /api/addresses/places/autocomplete?q=` – suggestions from configured provider
- `GET /api/addresses/places/details?place_id=` – normalized details for a selected suggestion

### Loader Script: Seeding Region Boundaries
- Script: `backend/scripts/load_region_boundaries.py`
  - Purpose: Load polygon datasets (e.g., NYC NTAs) into `region_boundaries`
  - Normalizes fields: `region_type`, `region_code`, `region_name`, `parent_region`, `boundary`, `centroid`, `region_metadata`
  - Reprojects to EPSG:4326 (WGS84) and upserts rows (idempotent)
  - Requirements: PostGIS‑enabled database, Python deps (`geopandas`, `shapely`, `psycopg2-binary`)

When to run:
- Not part of `backend/scripts/prep_db.py` (keep prep fast/deterministic)
- One‑time per environment and on‑demand when boundary sources update (or when adding new regions like SF/Toronto)

### Testing Strategy
- Unit/integration tests seed a tiny polygon via `RegionBoundaryRepository.insert_wkt` to avoid large datasets
- Mock provider used by default to avoid live API costs/instability; live tests gated by env flags
- Enrichment tests assert `district`, `neighborhood`, and `location_metadata` when the point falls within the test polygon

### Design Decisions Recap
- Removed NYC‑specific columns from addresses in favor of generic fields + `location_metadata`
- Single global `region_boundaries` table for any city
- Repository pattern for all DB access, including spatial queries
- Provider‑agnostic geocoding with consistent response model
- Frontend autocomplete UX fetches normalized details and auto‑fills form fields

### Operational Notes
- Ensure PostGIS is installed and enabled (migration checks and instructive error if missing)
- Country codes are normalized to ISO‑3166 alpha‑2 (`US`) to avoid inconsistent provider outputs
- The loader script is idempotent; safe to re‑run when updating boundaries
