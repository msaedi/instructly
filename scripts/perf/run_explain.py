#!/usr/bin/env python3
"""Run EXPLAIN (ANALYZE, BUFFERS, VERBOSE) for availability queries."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

import psycopg2
from psycopg2.extras import DictCursor

# Ensure backend package importable
BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings  # type: ignore

SQL_DIR = BASE_DIR / "scripts" / "perf" / "sql"
PLANS_DIR = BASE_DIR / "docs" / "perf" / "plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)


def load_sql(name: str) -> str:
    sql_path = SQL_DIR / name
    return sql_path.read_text()


def exec_explain(conn, sql: str, params: dict[str, object]) -> str:
    explain = f"EXPLAIN (ANALYZE, BUFFERS, VERBOSE) {sql.strip()}"
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(explain, params)
        rows: Sequence[Sequence[str]] = cur.fetchall()
    return "\n".join(row[0] for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EXPLAIN for availability queries")
    parser.add_argument("--instructor", required=True, help="Instructor UUID")
    parser.add_argument("--week-start", required=True, help="Week start (YYYY-MM-DD)")
    args = parser.parse_args()

    week_start = datetime.strptime(args.week_start, "%Y-%m-%d").date()
    week_end = week_start + timedelta(days=6)

    conn = psycopg2.connect(settings.get_database_url())
    conn.autocommit = True

    try:
        select_sql = load_sql("availability.sql").split(";\n\n")[0]
        select_plan = exec_explain(
            conn,
            select_sql,
            {
                "instructor_id": args.instructor,
                "week_start": week_start,
                "week_end": week_end,
            },
        )
        (PLANS_DIR / "week_get_plan.txt").write_text(select_plan)
        print("Week GET plan written to docs/perf/plans/week_get_plan.txt")

        delete_sql = load_sql("availability.sql").split(";\n\n")[1]
        dates = [week_start + timedelta(days=i) for i in range(7)]
        delete_plan = exec_explain(
            conn,
            delete_sql,
            {"instructor_id": args.instructor, "dates": dates},
        )
        (PLANS_DIR / "week_save_delete_plan.txt").write_text(delete_plan)
        print("Week SAVE delete plan written to docs/perf/plans/week_save_delete_plan.txt")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
