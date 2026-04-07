# InstaInstru Session Handoff v147
*Generated: April 6, 2026*
*Previous: v146 | Current: v147 | Next: v148*

## 🎯 Session v147 Summary

**Neighborhood Display Layer + Interactive Selector with Map**

This session built the user-facing neighborhood display system end-to-end: a 173-name display layer mapped from raw NYC NTA polygons, an alias-aware backend selector API, and an interactive frontend selector component with a click-to-select Leaflet map. Along the way we recovered test suite performance from 47 minutes back to 16, pushed coverage from 97.64% to 98.07%+, removed all `is_testing` coordinate fallbacks from production code, and stabilized auth/Redis test isolation.

| Objective | Status |
|-----------|--------|
| **Neighborhood mapping audit (173 display names from raw NTAs)** | ✅ Complete |
| **Backend display layer (Package 1)** | ✅ Merged via PR #401 |
| **Frontend interactive selector with map (Package 2)** | ✅ Merged via PR #402 |
| **Test suite slowdown (47 min → 16 min)** | ✅ Fixed |
| **Coverage recovery (97.64% → 98.07%+)** | ✅ Fixed |
| **Auth/Redis test isolation** | ✅ Fixed |
| **`is_testing` coordinate fallbacks** | ✅ Removed |
| **Near-me search DB session bypass** | ✅ Refactored |

---

## Phase 1: Neighborhood Mapping Audit (Complete)

Audited NYC NTA polygons and produced a final 173 user-friendly display names. 63 NTAs were dropped (parks, cemeteries, airports), the rest were consolidated and renamed using the user-facing convention.

### Key Files
- `/mnt/user-data/outputs/neighborhood-mapping-final.md` (v4)

### Key Decisions
- **Display key as stable API contract:** format `{market}-{borough}-{slug}`, immutable after first seed
- **Aliases embedded in selector API response**, not in a separate DB table
- **Configuration in importable Python module**, not in the database

---

## Phase 2: Backend Display Layer (Complete — PR #401)

**Branch:** `feat/neighborhood-display-layer`

Added the display column layer on top of `region_boundaries`, the alias-aware selector endpoint, the contract change for `service_areas/me`, location enrichment cleanup, search resolver dedupe, and a per-request region lookup preload.

### Backend Changes
- 3 new columns on `region_boundaries`: `display_name`, `display_key`, `display_order` (added to `005_search.py`, no new migration)
- `app/domain/neighborhood_config.py`: 262-entry mapping, `HIDDEN_ALIASES`, `CROSS_BOROUGH_ALIASES` (Marble Hill → Manhattan), `ABBREVIATION_VARIANTS`, `generate_display_key()`
- `app/domain/neighborhood_helpers.py`: extracted shared `_display_area_from_region` (DRY)
- `scripts/seed_neighborhood_display.py`: idempotent seeder with COALESCE key preservation
- New endpoint: `GET /api/v1/addresses/neighborhoods/selector?market=nyc` (Redis + HTTP cached, alias-aware)
- `PUT /service-areas/me` accepts `display_keys` (clean break, no backward compat)
- `GET /service-areas/me` returns display-level items
- Coverage labels use `COALESCE(display_name, region_name)`
- Point lookup excludes dropped polygons (`display_name IS NOT NULL`)
- Location enrichment: zero `nta_code`/`nta_name` references in app code
- Search resolver dedupe via `_dedupe_candidates_by_display()` across all 7 tiers
- `ResolvedLocation.region_ids` carries all backing polygon IDs
- `LocationCandidate` TypedDict split into base + `LocationCandidateDisplay` extension
- `RegionLookup.by_display_key` preload eliminates per-request DB query

### Key Files
- `backend/app/domain/neighborhood_config.py`
- `backend/app/domain/neighborhood_helpers.py`
- `backend/app/repositories/region_boundary_repository.py`
- `backend/app/services/address_service.py`
- `backend/app/services/search/location_resolver.py`
- `backend/app/routes/v1/addresses.py`
- `backend/scripts/seed_neighborhood_display.py`
- `backend/alembic/versions/005_search.py`

### Audit Loop
3 review rounds, all 11 CI findings resolved.

---

## Phase 3: Frontend Interactive Selector (Complete — PR #402)

**Branch:** `feat/neighborhood-selector-frontend`

Built the `NeighborhoodSelector` component matching the A-Team spec: two-panel layout (2/5 list, 3/5 map), interactive Leaflet map with click-to-select and bidirectional hover sync, alias-aware search with single-open accordion behavior in browse mode and expand-all-matches in search mode.

### Frontend Changes
- `NeighborhoodSelector` component: two-panel layout (list + map per A-Team spec)
- `BoroughSection`: single-open accordion (browse), expand-all-matches (search), Select all / Clear all per borough
- `NeighborhoodSearch`: alias-aware ranked matching (display_name > display_part > hidden_subarea > raw_nta > abbreviation), apostrophe normalization
- `NeighborhoodSelectorMap`: interactive Leaflet map, click-to-select, hover sync (bidirectional), dark mode tiles (Jawg dark via `prefers-color-scheme`), imperative `setStyle` via `layersByDisplayKey` ref (no remount), keyboard accessibility (Tab + Enter/Space)
- `useNeighborhoodSelectorData`, `useNeighborhoodPolygons` (with `enabled=showMap`), `useNeighborhoodSelection` hooks
- Controlled component with `value`/`defaultValue` async resync
- Selected polygons: brand lavender fill (#F3E8FF) + purple border (#7E22CE), light + dark mode
- Long-name pills: `col-span-2` when `length > 21 || segments >= 2` (57 items full-width)
- No +/✓ icons — selection conveyed via color only
- Minimum selection guard: last neighborhood can't be deselected (Sonner toast)
- Hidden scrollbar on list panel
- Onboarding zip-based preselection via `GET /neighborhoods/lookup?lat&lng&market`
- All 4 consumers migrated (onboarding, profile, modal, apply)
- `ServiceAreasCard.tsx` and `serviceAreaSelector.ts` deleted
- 5 E2E test files updated

### Backend Additions for Package 2
- `GET /api/v1/addresses/neighborhoods/polygons?market=nyc` (simplified GeoJSON, tolerance 0.001, Redis cached)
- `GET /api/v1/addresses/neighborhoods/lookup?lat&lng&market` (point → display_key, with bounds validation, wraps `find_region_by_point` via `find_neighborhood_by_point` service method)

### Key Files
- `frontend/components/neighborhoods/NeighborhoodSelector.tsx`
- `frontend/components/neighborhoods/NeighborhoodSelectorMap.tsx`
- `frontend/components/neighborhoods/BoroughSection.tsx`
- `frontend/components/neighborhoods/NeighborhoodSearch.tsx`
- `frontend/hooks/useNeighborhoodSelectorData.ts`
- `frontend/hooks/useNeighborhoodPolygons.ts`
- `frontend/hooks/useNeighborhoodSelection.ts`
- `frontend/features/instructor-profile/InstructorProfileForm.tsx`

### Audit Loop
4 review rounds, all 12 CI findings + 5 visual fixes + 9 A-Team spec alignment items resolved.

---

## Phase 4: Direct-to-Main Nits (Complete)

Six low-risk nits committed directly to main after both PRs landed:

1. **Batch N+1 query** in `find_region_ids_by_partial_names` (VALUES CTE + ROW_NUMBER, kept dict mapping API for AuthService)
2. **`aria-controls`** on borough accordion headers
3. **`aria-live`** region for search count (uses `matchByKey.size` to avoid Marble Hill double-counting)
4. **Query keys registry** (`queryKeys.neighborhoods.selector/polygons`)
5. **`queryFn` wrapper** migration
6. **Sonner toast** for minimum selection guard

---

## Phase 5: Test Infrastructure Stabilization (Complete)

### Test Slowdown: 47 min → 16 min
- Removed `_normalize_region_boundaries_to_canonical_nyc(cleanup_db)` from per-test `cleanup_test_database()` at `tests/conftest.py:1665`. Was running 262 DB ops × 13,575 tests ≈ 3.5M extra operations. Session-scoped normalization at startup is sufficient.
- Added dirty check to `_ensure_boundary_columns()` to skip UPDATE+flush when display values are already correct.

### CI Test Failure: `test_neighborhood_lookup_route`
- Rewrote to be self-contained — seeds own `RegionBoundary` with known polygon, computes centroid in Python, looks up that point, asserts exact response, deletes in `finally` block. No longer depends on hardcoded coordinates landing on seeded data.
- Also fixed `test_service_areas_geojson_and_neighborhoods` (hardcoded `== 199` → config-driven).

### Coverage Recovery: 97.64% → 98.07%
173 new bug-hunting tests across 8 new + 4 modified test files. Targeted neighborhood files (`location_resolver`, `filter_service`, `address_service`, `region_boundary_repository`, `location_tier4`, `neighborhood_helpers`) **plus** the 4 decomposition files extracted from `main.py` (`background_jobs.py` at 20% was the biggest gap, `lifespan.py`, `internal_metrics.py`, `middleware_setup.py`).

### Auth/Redis 401 Failures
- `TokenBlacklistService.is_revoked` is fail-closed: returns `True` when Redis is unavailable. Other tests monkeypatching `settings.redis_url` to `None` corrupted Redis state for subsequent tests.
- Added session-scoped autouse fixture in `tests/conftest.py:116` patching async `is_revoked` to return `False`.
- Added `real_token_blacklist` opt-out fixture for 9 tests that explicitly verify revocation behavior.
- Used `unittest.mock.patch.object` (not monkeypatch) for session scope.

### `test_search_near_me_uses_default_address`
Initially fixed with a `settings.is_testing` branch in `search.py` so the search route uses the request-scoped `db` session for default-address lookup in tests. Then properly refactored: `_get_user_address` now accepts `db: Session` from the route's injected `Depends(get_db)`, called via `await asyncio.to_thread(...)`. The `is_testing` branch and TODO are gone.

### `is_testing` Coordinate Fallbacks Removed
- Removed 2 `is_testing` branches from `app/services/address_service.py`:
  - Create path lines 189–194 (hardcoded Midtown coords 40.7580/-73.9855, forced `verification_status="verified"`)
  - Update path lines 254–257 (hardcoded 0.0/0.0, forced verified)
- Tests now use explicit mocked geocoder results or pre-set lat/lng.
- Removed unused `settings` import from `address_service.py`.
- **Zero `is_testing` branches remain in `address_service.py`.**
- **Zero `is_testing` branches remain in `search.py`** (was 1 after Phase 5 fix, now 0 after refactor).

### UI Fixes (Frontend Commit)
- **Service Areas accordion:** changed `openServiceAreas` initial state from hardcoded `true` to `false` in `InstructorProfileForm.tsx:177`. Dashboard now starts collapsed.
- **Fit map button:** moved to dedicated bottom-right overlay layer in `NeighborhoodSelectorMap.tsx:361` with `pointer-events-auto`. Was being covered by Leaflet zoom controls during repaint due to z-index conflict.

---

## 📊 Platform Health (Post-v147)

| Metric | Value | Change from v146 |
|--------|-------|---------------------|
| **Backend tests** | 13,748 | +173 |
| **Backend coverage** | 98.07% | +0.43% (recovered from 97.64%) |
| **Frontend tests** | 8,517+ | +regression tests for new components |
| **Frontend type coverage** | 100% | unchanged |
| **Test suite time** | ~16 min | -31 min (recovered from 47 min) |
| **Display names** | 173 | new (across 5 boroughs) |
| **NTAs dropped** | 63 | new (parks, cemeteries, airports) |
| **`is_testing` branches in production** | 0 in `address_service.py`, 0 in `search.py` | -3 total |

---

## 🏛️ Architecture Decisions

### New ADRs from this session:

- **Display key as stable API contract** — Format `{market}-{borough}-{slug}`. Immutable after first seed. Aliases live in the selector API response, not in a separate DB table.

- **Configuration over data tables** — Neighborhood display config lives in an importable Python module (`neighborhood_config.py`), not in PostgreSQL. Avoids needing migrations for display tweaks and keeps the mapping under code review.

- **Search resolver dedupes by `display_key` at aggregation layer** — All 7 resolution tiers feed into a single `_dedupe_candidates_by_display()` step. This means consolidated neighborhoods never appear twice in results.

- **Imperative `setStyle` for map updates** — The Leaflet map uses an imperative `layersByDisplayKey` ref to update polygon styles on selection change rather than remounting the GeoJSON layer. Avoids flicker and preserves user pan/zoom state.

- **Single-open accordion in browse, expand-all-matches in search** — Browse mode keeps the UI tidy with one open borough at a time. Search mode expands every borough containing a match so users can see all results without clicking. Original state is restored when search clears.

- **No new Alembic migration** — `005_search.py` was edited in place and the schema rebuilt, since no production data exists. This is the standing project rule but worth noting because the new columns are non-nullable.

- **Clean break, zero backward compatibility** — `service_areas/me` accepts only `display_keys`, never the old region IDs. All 4 consumers migrated in the same PR. `ServiceAreasCard.tsx` and `serviceAreaSelector.ts` deleted entirely.

- **Session-scoped autouse blacklist bypass for tests** — Tests should never depend on Redis-backed revocation state. Tests that explicitly verify revocation behavior opt out via `real_token_blacklist` fixture.

- **Geocoder mocking in tests, never `is_testing` branches in production code** — The geocoder is either called (production) or mocked (tests). No middle ground. Production code does not know it is being tested.

- **`_get_user_address` accepts injected `db` parameter** — The route's injected request session is the source of truth for the near-me default-address lookup. Eliminates the `get_db_session()` bypass and the temporary `is_testing` branch.

- **`additional_boroughs` rendering during search** — Marble Hill matches surface under Manhattan during active search via the `additional_boroughs` field on the alias config.

- **Selection state controlled with `value`/`defaultValue` props** — Async resync via `useMemo`/`useEffect` so the selector can be driven from React Query data without losing intermediate user changes.

- **Map polygons keyboard-accessible** — Tab to focus, role="button", Enter/Space to toggle, focus syncs hover state. (Arrow key navigation deferred — requires polygon adjacency graph.)

---

## 📋 Remaining Work

| Item | Priority | Notes |
|------|----------|-------|
| **Map arrow key navigation** | Medium / accessibility | Requires computing polygon adjacency graph via `ST_Touches` between all pairs, then mapping arrow directions to nearest neighbor by centroid position. Currently keyboard supports Tab + Enter/Space only. WCAG enhancement, not a launch blocker. Defer to a future accessibility pass. |
| **Overly broad exception handling sweep** | Low / codebase-wide | Pattern flagged by Claude bot during review. Not neighborhood-specific. Track separately as a refactor task across the entire codebase. |
| **Package D (NL search pipeline hardening)** | Carryover from v145 | Not touched in v147. Still in progress. |
| **PRD completion** | Carryover | 10-part skeleton exists; coding agent to mine codebase for ~60% of content. |
| **Tracks 2 and 3 of database protection plan** | Carryover | Investigation and implementation prompts already generated, not executed. |
| **Founding instructor activation codes delivery** | Carryover | Instantly campaign in Draft, 102 contacts imported. |
| **Nina's LinkedIn authority sequence** | Carryover | 9-post calendar, iNSTAiNSTRU not named until Post 9. |
| **SEO programmatic page strategy** | Carryover | Subject-first URL hierarchy, neighborhood × service pages. |

### Completed in v147 (previously deferred):
- ✅ DRY `_display_area_from_region` extraction
- ✅ `LocationCandidate` TypedDict split
- ✅ All 11 Package 1 CI review findings
- ✅ All 12 Package 2 CI review findings
- ✅ Test slowdown (47 → 16 min)
- ✅ CI lookup test self-contained
- ✅ Coverage 97.64% → 98.07%
- ✅ Auth/Redis 401 fixture
- ✅ Near-me test refactor (proper, no `is_testing` branch)
- ✅ `is_testing` coordinate fallbacks removed
- ✅ Service areas accordion collapsed on dashboard load
- ✅ Fit map button z-index
- ✅ All 6 direct-to-main nits

---

**STATUS: Neighborhood display layer + interactive selector shipped end-to-end. Test infrastructure stabilized. Production code is `is_testing`-free for address handling. Ready for Package D continuation or next feature.**
