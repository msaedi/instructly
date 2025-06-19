#!/usr/bin/env python3
"""Check the actual column type for areas_of_service"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402

engine = create_engine(settings.database_url)

with engine.connect() as conn:
    result = conn.execute(
        text(
            """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = 'instructor_profiles'
        AND column_name = 'areas_of_service';
    """
        )
    )

    for row in result:
        print(f"Column: {row[0]}")
        print(f"Data type: {row[1]}")
        print(f"UDT name: {row[2]}")

    # Also check a sample
    result = conn.execute(
        text(
            """
        SELECT areas_of_service
        FROM instructor_profiles
        WHERE areas_of_service IS NOT NULL
        LIMIT 1;
    """
        )
    )

    for row in result:
        print(f"\nSample value: {row[0]}")
        print(f"Type: {type(row[0])}")
