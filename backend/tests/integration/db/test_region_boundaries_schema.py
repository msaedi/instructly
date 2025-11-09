# backend/tests/integration/db/test_region_boundaries_schema.py
"""Regression tests for region_boundaries schema guarantees."""

from sqlalchemy import text


def test_region_boundaries_has_unique_index(db):
    """Ensure UNIQUE(region_type, region_code) exists for UPSERT reliability."""
    rows = db.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename='region_boundaries'
            """
        )
    ).fetchall()

    names = {row[0] for row in rows}
    assert (
        "region_boundaries_rtype_rcode_idx" in names
    ), "region_boundaries_rtype_rcode_idx must exist for loader ON CONFLICT to work"
