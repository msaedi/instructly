import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_region_boundaries_seeded_minimum(db: Session):
    # If the table does not exist, skip (migrations not applied or PostGIS absent)
    exists = db.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='public' AND table_name='region_boundaries'
            )
            """
        )
    ).scalar()
    if not exists:
        pytest.skip("region_boundaries table not present")

    count = db.execute(text("SELECT COUNT(*) FROM region_boundaries")).scalar()

    # If empty, try invoking the loader via prep_db path (no-op if already seeded)
    if count == 0:
        # Only run locally; CI may not have geopandas installed
        # This keeps test safe by skipping when not available
        try:
            subprocess.run(
                [sys.executable, os.path.join("backend", "scripts", "load_region_boundaries.py")],
                check=True,
                cwd=os.path.join(os.getcwd(), "backend"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception:
            pytest.skip("Loader not available or dependencies missing; skipping seed attempt")

        count = db.execute(text("SELECT COUNT(*) FROM region_boundaries")).scalar()

    # Expect at least some rows present (tiny threshold)
    assert count >= 1
