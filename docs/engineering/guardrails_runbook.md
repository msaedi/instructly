# Guardrails Runbook (Privacy, CI, and Trunk Dev)

## Privacy Protection Audit – how to run
- **Triggers:** push to `main`, PRs to `main`, and manual dispatch.
- **Invariants enforced by CI (Workflow Lint):**
  - Uses **Docker Compose v2** (never `docker-compose` v1).
  - **DB image pinned by digest** and guarded in the workflow.
  - Triggers (push + PR to `main`) must exist.
- **Manual run:** Actions → *Privacy Protection Audit* → *Run workflow*.
- **What it does:** GHCR login → start DB (pgvector+postgis) → health/TCP waits → migrate & seed → run privacy audit → upload artifacts.
- **Artifacts:** `backend/logs/privacy_audit_report.json` and `.md`.

## Bumping the Privacy DB image (manual, no cron)
1. Actions → *Privacy DB Image Bump* → *Run workflow* (input: `tag`, e.g. `14-postgis-pgvector`).
2. The job resolves the tag to a **digest**, updates the workflow, and opens a PR if the digest changed (no-op otherwise).
3. Merge the PR; Privacy + Workflow Lint run automatically.

## GHCR access tips
- The GHCR package is linked to this repo; default `GITHUB_TOKEN` works.
- If ever denied, either re-link the package or add a repo secret `GHCR_PAT` with `read:packages`.

## Troubleshooting (fast paths)
- **“docker-compose: not found”** → some workflow still uses v1. Fix to `docker compose`. Workflow Lint will flag it.
- **Vector/PostGIS missing** → DB image not pinned/resolved; Workflow Lint guard should catch this. Re-pin via bump workflow.
- **Flaky DB bring-up** → the workflow already does health + TCP waits. If needed, increase retries/sleep slightly.

## Date/Time safety (payments)
- Tests lock the 24h boundary:
  - `23h59m` → `authorizing`
  - `24h01m` → `scheduled`
- Route + service tests exist; time math is deterministic.

## Trunk-based dev (current mode)
- Push to `main` by default.
- Open PRs only for risky changes (migrations/behavior/large diffs).
- Pre-push tip: `FAST_HOOKS=1 pre-commit run --all-files`.
