# Search Tracking E2E Tests

This directory contains comprehensive end-to-end tests for the search tracking system.

## Test Files

### 1. `test_search_tracking_comprehensive.py`
The original comprehensive test suite covering:
- Hybrid model (deduplication + full tracking)
- All 5 search types
- Analytics enhancement
- Referrer tracking
- Session tracking

### 2. `test_search_tracking_e2e.py` ✨ NEW
Complete e2e flows testing:
- **All 5 search types** for both authenticated and guest users (10 scenarios)
- **Search deduplication** with same query different types
- **Interaction tracking** with correct time calculations
- **Different interaction types** (click, hover, view_profile, book)
- **Analytics data collection** (device context, geolocation, session continuity)

### 3. `test_search_tracking_edge_cases_e2e.py` ✨ NEW
Edge cases and error scenarios:
- **Input validation** (empty queries, invalid types, negative counts)
- **Unicode handling** (Chinese, Arabic, emojis)
- **Concurrency** (duplicate searches, rapid interactions)
- **Data integrity** (soft deletes, guest conversion)
- **Privacy** (IP hashing, returning user detection)

## Running the Tests

### Run all e2e tests:
```bash
cd backend
python scripts/run_search_tracking_e2e_tests.py
```

### Run specific test file:
```bash
pytest tests/integration/test_search_tracking_e2e.py -v
```

### Run specific test:
```bash
pytest tests/integration/test_search_tracking_e2e.py::TestSearchTypeE2E::test_type1_natural_language_search_e2e -v
```

### Run with coverage:
```bash
pytest tests/integration/test_search_tracking_*.py --cov=app.services.search_history_service --cov-report=html
```

## Test Scenarios Covered

### 1. Natural Language Search (`search_type: natural_language`)
- User types in search bar
- Both authenticated and guest users
- Verifies search event ID is returned
- Tests deduplication on repeated searches

### 2. Category Selection (`search_type: category`)
- Clicking categories on homepage (Music, Sports, etc.)
- No initial results count
- Correct referrer tracking

### 3. Service Pills - Homepage (`search_type: service_pill`)
- Top 7 services on homepage
- Tracks which service was clicked
- Includes results count

### 4. Services Page Items (`search_type: service_pill`)
- Full service list on /services page
- Same type as homepage pills but different referrer
- Helps distinguish traffic source

### 5. Search History Click (`search_type: search_history`)
- Clicking on recent searches
- Creates new event with search_history type
- Maintains search continuity

## Key Features Tested

### Search Event ID
- Every search returns a `search_event_id`
- Used for tracking interactions
- Essential for CTR calculations

### Time Tracking
- `time_to_interaction` in seconds
- Calculated from search timestamp
- Helps measure search effectiveness

### Device Context
- Viewport size
- Connection type
- Screen resolution
- Browser information

### Session Tracking
- Browser session ID links searches
- Shows user journey
- Guest sessions persist 30 days

## Common Issues and Solutions

### Issue: No search_event_id returned
**Solution**: Ensure backend returns the event ID in response:
```python
result.search_event_id = event.id
```

### Issue: Interaction not recorded
**Solution**: Check that:
1. Search event ID is valid
2. Instructor ID is the user_id, not profile id
3. Time is calculated correctly (elapsed seconds)

### Issue: Double counting
**Solution**: Hybrid model ensures:
- `search_history`: Deduplicated (one entry per unique query)
- `search_events`: Full tracking (every search recorded)

## Database Schema Reference

### search_history
- Deduplicated user searches
- Tracks search_count
- Soft delete support

### search_events
- Every search interaction
- Analytics data
- Append-only (no deletes)

### search_interactions
- User interactions with results
- Links to search_events
- Tracks CTR and engagement
