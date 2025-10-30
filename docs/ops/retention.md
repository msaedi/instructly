# Retention & Soft-Delete Purge

This job permanently deletes rows that have already been soft-deleted (`deleted_at` populated) once they are older than the configured retention window. It should be run regularly (e.g., nightly via cron) to keep the database lean and to honour privacy/retention policies.

## Running the purge

All commands assume you are in the repository root.

```bash
cd backend
python scripts/retention/purge_soft_deleted.py --dry-run
```

**Recommended workflow**

1. **Dry run first** – inspect the counts per table to ensure the purge scope is expected:
   ```bash
   python scripts/retention/purge_soft_deleted.py --dry-run --days 45
   ```
2. **Execute the purge** – once satisfied with the counts:
   ```bash
   python scripts/retention/purge_soft_deleted.py --days 45 --chunk 2000
   ```
3. **Automate** – the script is idempotent. Configure a cron/Celery beat entry that runs nightly with production-safe defaults (e.g., `--days 45 --chunk 2000`). The job logs all activity and clears cache namespaces (`avail:*`, `catalog:*`, `booking_stats:*`, `favorites:*`) after each table finishes.

Use `--json` if you need structured output (for dashboards or observability hooks).

## Scheduled via Celery Beat

- The Celery task `retention.purge_soft_deleted` runs nightly (default `0 4 * * *`, 04:00 UTC) via Beat.
- Configuration knobs (environment variables):
  - `RETENTION_PURGE_DAYS` (default `30`)
  - `RETENTION_PURGE_CHUNK` (default `1000`)
  - `RETENTION_PURGE_DRY_RUN` (default `false`)
  - `RETENTION_PURGE_CRON` (default `0 4 * * *`)
  - `CELERY_RETENTION_QUEUE` (default `maintenance`)
- Example Beat entry (applied automatically):
  ```python
  "nightly-retention-purge": {
      "task": "retention.purge_soft_deleted",
      "schedule": crontab(hour=4, minute=0),
      "options": {"queue": "maintenance"},
  }
  ```
- To run a dry run for a single night, set `RETENTION_PURGE_DRY_RUN=true` (or override via the task kwargs) and monitor the logs before resetting the env var.
- The task logs per-table counts and metadata to the Celery worker logs (look for `Retention purge completed`). Failures emit an exception trace and are retried up to three times.

## Safety notes

- **Chunked deletes**: each table is processed in independent transactions and capped at `--chunk` rows per commit. Increase `--chunk` for larger batches if the database can tolerate it.
- **Cache invalidation**: cache prefixes are cleared immediately after a table’s rows are purged to avoid stale availability/booking/service reads.
- **SQLite friendly**: the purge uses reflected metadata and plain SQLAlchemy deletes, so it works against SQLite (our CI + local default) and PostgreSQL.
- **Dry-run mode**: no rows are removed, but counts are aggregated using the same filters the real purge uses.

## Typical durations

| Environment | Settings            | Notes                                                     |
|-------------|---------------------|-----------------------------------------------------------|
| Local (SQLite) | `--dry-run`         | < 1s for default fixtures (most tables skip).             |
| Local (Postgres) | `--days 45 --chunk 1000` | Usually < 5s unless there is a large backlog.            |
| Production | `--days 60 --chunk 2000` | Plan for ~10–20s; monitor logs & metrics for row counts. |

Keep historical summaries by shipping the JSON output into your monitoring stack; the `_meta` block includes cutoff timestamp, chunk size, and dry-run flag for easy alerting.
