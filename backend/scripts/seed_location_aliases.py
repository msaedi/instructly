#!/usr/bin/env python3
"""
Seed `location_aliases` from `backend/data/location_aliases.json`.

`region_boundaries` remains the canonical source of neighborhood names; this seeder
only populates abbreviations/colloquialisms that should resolve to a specific region.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import ulid

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "location_aliases.json"


def _normalize(text_value: str) -> str:
    return " ".join(str(text_value).strip().lower().split())


def _load_aliases(data_path: Path) -> dict[str, Any]:
    with data_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def seed_location_aliases(
    engine,
    *,
    verbose: bool = True,
    region_code: str = "nyc",
    data_path: Path = DEFAULT_DATA_PATH,
) -> int:
    """
    Seed `location_aliases` for the given region_code.

    Returns the number of INSERT attempts (best-effort; idempotent via ON CONFLICT).
    """
    payload = _load_aliases(data_path)
    aliases = payload.get("aliases") or []
    if not isinstance(aliases, list):
        raise ValueError("Invalid location_aliases.json: 'aliases' must be a list")

    inserted = 0
    skipped_region = 0
    skipped_duplicate = 0
    missing_region = 0

    with Session(engine) as session:
        rows = session.execute(
            text(
                """
                SELECT id, region_name
                FROM region_boundaries
                WHERE region_type = :rtype
                  AND region_name IS NOT NULL
                """
            ),
            {"rtype": region_code},
        ).fetchall()
        name_to_id = {str(r[1]).strip().lower(): str(r[0]) for r in rows if r[1]}

        def _find_region_id(region_name: str) -> str | None:
            key = _normalize(region_name)
            if key in name_to_id:
                return name_to_id[key]
            # Best-effort normalization (e.g., "Astoria (Central)" -> "Astoria").
            candidates = [
                rid for existing_name, rid in name_to_id.items() if key in existing_name or existing_name in key
            ]
            if len(candidates) == 1:
                return candidates[0]
            return None

        seen_aliases: set[str] = set()

        for row in aliases:
            if not isinstance(row, dict):
                continue

            alias = _normalize(row.get("alias", ""))
            region_name = str(row.get("region_name", "")).strip()
            alias_type = str(row.get("type") or row.get("alias_type") or "abbreviation").strip().lower()

            if not alias or not region_name:
                continue

            if alias in seen_aliases:
                skipped_duplicate += 1
                continue
            seen_aliases.add(alias)

            region_id = _find_region_id(region_name)
            if not region_id:
                missing_region += 1
                if verbose:
                    print(f"  ⚠ Region not found for alias '{alias}': '{region_name}'")
                continue

            try:
                session.execute(
                    text(
                        """
                        INSERT INTO location_aliases (id, alias, region_boundary_id, alias_type)
                        VALUES (:id, :alias, :region_boundary_id, :alias_type)
                        ON CONFLICT (alias) DO NOTHING
                        """
                    ),
                    {
                        "id": str(ulid.ULID()),
                        "alias": alias,
                        "region_boundary_id": region_id,
                        "alias_type": alias_type,
                    },
                )
                inserted += 1
            except Exception as e:
                skipped_region += 1
                if verbose:
                    print(f"  ⚠ Could not insert alias '{alias}': {e}")

        session.commit()

    if verbose:
        print(f"  ✓ Seeded {inserted} location aliases ({region_code})")
        if skipped_duplicate:
            print(f"    - Skipped duplicates in JSON: {skipped_duplicate}")
        if missing_region:
            print(f"    - Skipped (missing region_boundaries row): {missing_region}")
        if skipped_region:
            print(f"    - Skipped (insert errors): {skipped_region}")

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed location_aliases from JSON.")
    parser.add_argument("--region-code", default="nyc", help="Region code to seed (matches region_boundaries.region_type)")
    parser.add_argument("--db-url", default=None, help="Override database URL (defaults to settings)")
    parser.add_argument("--data-path", default=str(DEFAULT_DATA_PATH), help="Path to location_aliases.json")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        # Ensure backend/ is importable when called directly.
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from app.core.config import settings  # noqa: PLC0415

        db_url = settings.get_database_url()

    engine = create_engine(db_url)
    seed_location_aliases(
        engine,
        verbose=not args.quiet,
        region_code=str(args.region_code).strip().lower(),
        data_path=Path(args.data_path),
    )


if __name__ == "__main__":
    main()
