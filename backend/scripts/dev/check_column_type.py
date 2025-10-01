#!/usr/bin/env python3
"""Quick diagnostics for instructor service areas after legacy field removal."""

from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402

engine = create_engine(settings.database_url)

with engine.connect() as conn:
    try:
        probe = conn.execute(text("SELECT instructor_id, neighborhood_id FROM instructor_service_areas LIMIT 1"))
        first = probe.fetchone()
    except SQLAlchemyError as exc:
        print("❌ Unable to query instructor_service_areas:", exc)
        sys.exit(1)

    total = conn.execute(text("SELECT COUNT(*) FROM instructor_service_areas"))
    count = total.scalar_one()
    print(f"instructor_service_areas rows: {count}")

    if first:
        sample = conn.execute(
            text(
                """
                SELECT isa.instructor_id, isa.neighborhood_id, rb.region_name, rb.parent_region
                FROM instructor_service_areas AS isa
                LEFT JOIN region_boundaries AS rb ON rb.id = isa.neighborhood_id
                ORDER BY isa.created_at DESC
                LIMIT 3
                """
            )
        ).fetchall()
        print("Sample service areas:")
        for row in sample:
            instructor_id, neighborhood_id, region_name, parent_region = row
            print(
                f"  instructor={instructor_id} neighborhood={neighborhood_id} "
                f"name={region_name!r} borough={parent_region!r}"
            )
    else:
        print("No instructor service areas found yet (table reachable but empty).")

    borough = conn.execute(
        text(
            """
            SELECT id, region_name, parent_region
            FROM region_boundaries
            WHERE region_type = :region_type
              AND parent_region = :borough
            ORDER BY region_name
            LIMIT 1
            """
        ),
        {"region_type": "nyc", "borough": "Manhattan"},
    ).fetchone()

    if borough:
        borough_id, borough_name, parent_region = borough
        print(
            "Reference borough:",
            f"id={borough_id} name={borough_name!r} parent={parent_region!r}",
        )
    else:
        print("⚠️ Unable to find a Manhattan entry in region_boundaries.")
