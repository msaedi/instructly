#!/usr/bin/env python3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

query = text(
    """
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('bookings', 'availability_slots', 'instructor_availability')
ORDER BY tablename, indexname
"""
)

with engine.connect() as conn:
    result = conn.execute(query)
    print(f"{'Table':<30} {'Index':<50}")
    print("=" * 80)
    for row in result:
        print(f"{row.tablename:<30} {row.indexname:<50}")
        print(f"    Definition: {row.indexdef}")
        print()
