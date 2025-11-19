# Render Deployment & Health Checks

Render should point its health check to `/live`. This endpoint is DB-free — it never touches
Postgres, Supabase, or Redis — so brief pooler hiccups or SSL reconnects won’t kill the process.

Use `/ready` only for deeper diagnostics (CI, manual smoke tests, etc.). `/ready` verifies the
database and cache dependencies, so it can intentionally fail when Supabase or Redis is offline.
