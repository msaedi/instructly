# Pre-Existing Issues Tracker

## Search History Dedup Semantics
- `SearchHistoryRepository.find_existing_search()` matches the raw `search_query` value.
- `SearchHistoryRepository.create()` and `SearchHistoryRepository.upsert_search()` rely on normalized query behavior.
- This inconsistency predates the repository cleanup and decomposition work.
- It is tracked here and intentionally not fixed in this change.
