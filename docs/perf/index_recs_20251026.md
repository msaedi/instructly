# Availability Query Plans & Index Recommendations (2025-10-26)

## Captured Plans
- `docs/perf/plans/week_get_plan.txt`: `SELECT ... FROM availability_slots WHERE instructor_id=? AND specific_date BETWEEN ? AND ? ORDER BY ...`
- `docs/perf/plans/week_save_delete_plan.txt`: delete by `instructor_id` + date array before bulk insert.

## Proposed Indexes
1. `availability_slots (instructor_id, specific_date, start_time)`
   - Speeds week reads and deletes with range filter.
   - DDL: `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_slots_instructor_date_start ON availability_slots (instructor_id, specific_date, start_time);`
   - Risk: Extra write cost on insert/delete; plan to monitor bloat via `pg_stat_all_indexes`.

2. `availability_slots (instructor_id, specific_date)` partial for recent weeks (optional)
   - `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_slots_recent_weeks ON availability_slots (instructor_id, specific_date) WHERE specific_date >= CURRENT_DATE - INTERVAL '30 days';`
   - Good if majority of traffic hits current month; ensure autovacuum keeps partial index small.

3. If delete uses `specific_date = ANY($1)` frequently, consider temporary table + join to reuse the same index.

Rollback: `DROP INDEX CONCURRENTLY IF EXISTS idx_slots_instructor_date_start;`
