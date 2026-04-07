from __future__ import annotations

import json

from scripts.seed_location_aliases import seed_location_aliases
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def _setup_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE region_boundaries (
                    id TEXT PRIMARY KEY,
                    region_type TEXT NOT NULL,
                    region_name TEXT,
                    display_name TEXT,
                    display_key TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE location_aliases (
                    id TEXT PRIMARY KEY,
                    city_id TEXT NOT NULL,
                    alias_normalized TEXT NOT NULL,
                    region_boundary_id TEXT,
                    requires_clarification BOOLEAN NOT NULL,
                    candidate_region_ids TEXT,
                    status TEXT NOT NULL,
                    confidence FLOAT NOT NULL,
                    source TEXT NOT NULL,
                    user_count INTEGER NOT NULL,
                    alias_type TEXT,
                    updated_at TEXT,
                    deprecated_at TEXT,
                    UNIQUE(city_id, alias_normalized)
                )
                """
            )
        )
    return engine


def test_seed_location_aliases_resolves_single_display_group(tmp_path) -> None:
    engine = _setup_engine()
    payload = {
        "region_code": "nyc",
        "city_id": "city-1",
        "aliases": [
            {
                "alias": "ues",
                "region_name": "Upper East Side",
                "type": "abbreviation",
                "confidence": 1.0,
            }
        ],
        "ambiguous_aliases": [],
    }
    data_path = tmp_path / "location_aliases.json"
    data_path.write_text(json.dumps(payload), encoding="utf-8")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO region_boundaries (id, region_type, region_name, display_name, display_key)
                VALUES
                    ('r2', 'nyc', 'Upper East Side-Yorkville', 'Upper East Side', 'nyc-manhattan-upper-east-side'),
                    ('r1', 'nyc', 'Upper East Side-Carnegie Hill', 'Upper East Side', 'nyc-manhattan-upper-east-side'),
                    (
                        'r3',
                        'nyc',
                        'Upper East Side-Lenox Hill-Roosevelt Island',
                        'Upper East Side / Roosevelt Island',
                        'nyc-manhattan-upper-east-side-roosevelt-island'
                    )
                """
            )
        )

    inserted = seed_location_aliases(
        engine,
        verbose=False,
        region_code="nyc",
        data_path=data_path,
    )

    assert inserted == 1

    with Session(engine) as session:
        row = session.execute(
            text(
                """
                SELECT region_boundary_id, requires_clarification, candidate_region_ids
                FROM location_aliases
                WHERE city_id = :city_id AND alias_normalized = :alias
                """
            ),
            {"city_id": "city-1", "alias": "ues"},
        ).mappings().one()

    assert row["region_boundary_id"] == "r1"
    assert bool(row["requires_clarification"]) is False
    assert json.loads(str(row["candidate_region_ids"])) == ["r2"]
