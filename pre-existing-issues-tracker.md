# Pre-Existing Issues Tracker

## Search History Dedup Semantics
- `SearchHistoryRepository.find_existing_search()` matches the raw `search_query` value.
- `SearchHistoryRepository.create()` and `SearchHistoryRepository.upsert_search()` rely on normalized query behavior.
- This inconsistency predates the repository cleanup and decomposition work.
- It is tracked here and intentionally not fixed in this change.

## Auth Cache Subject Lookup Performance
- `auth_cache.py` `lookup_user_by_subject_nonblocking()` falls back to a direct DB lookup for email subjects.
- That email-subject path bypasses Redis caching and can hit the database on every call under load.
- This is a pre-existing performance risk and is intentionally out of scope for the current PR.

## Final Adverse Action Worker Transaction Boundary
- `background_check_workflow_service.py` `_execute_final_adverse_action()` needs a dedicated review for worker transaction isolation.
- Codex flagged a risk that using `self.repo.db` instead of a fresh `SessionLocal()` in the worker path could leave jobs stuck as `running` if the worker dies between commits.
- Verify the worker-path transaction boundary and fix it in a dedicated follow-up PR.
