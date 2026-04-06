#!/usr/bin/env python3
"""Populate display-layer columns on NYC region boundaries."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.domain.neighborhood_config import (  # noqa: E402
    NEIGHBORHOOD_MAPPING,
    generate_display_key,
)


def seed_neighborhood_display(
    engine: Any,
    *,
    region_type: str = "nyc",
    market: str = "nyc",
    verbose: bool = True,
) -> dict[str, int]:
    """Populate neighborhood display-layer metadata on region boundaries."""

    with Session(engine) as session:
        rows = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT id, parent_region, region_name, display_name, display_key
                    FROM region_boundaries
                    WHERE region_type = :region_type
                    ORDER BY parent_region, region_name, id
                    """
                ),
                {"region_type": region_type},
            ).mappings()
        ]

        actual_keys = {
            (str(row["parent_region"]), str(row["region_name"]))
            for row in rows
            if row["parent_region"] is not None and row["region_name"] is not None
        }
        expected_keys = set(NEIGHBORHOOD_MAPPING.keys())

        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        if missing or unexpected:
            details: list[str] = ["Neighborhood display mapping mismatch."]
            if missing:
                details.append(f"Missing from DB ({len(missing)}): {missing[:10]}")
            if unexpected:
                details.append(f"Unexpected in DB ({len(unexpected)}): {unexpected[:10]}")
            raise ValueError(" ".join(details))

        mapped_count = 0
        dropped_count = 0
        display_names_by_borough: dict[str, set[str]] = defaultdict(set)
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

        for row in rows:
            borough = str(row["parent_region"])
            region_name = str(row["region_name"])
            display_name = NEIGHBORHOOD_MAPPING[(borough, region_name)]
            row["mapped_display_name"] = display_name
            if display_name is None:
                dropped_count += 1
                continue
            mapped_count += 1
            display_names_by_borough[borough].add(display_name)
            groups[(borough, display_name)].append(row)

        display_order_by_group: dict[tuple[str, str], int] = {}
        for borough, display_names in display_names_by_borough.items():
            for index, display_name in enumerate(sorted(display_names)):
                display_order_by_group[(borough, display_name)] = index

        group_key_by_group: dict[tuple[str, str], str] = {}
        preserved_groups = 0
        new_groups = 0
        for group_key, group_rows in groups.items():
            existing_keys = {
                str(row["display_key"]).strip()
                for row in group_rows
                if row.get("display_key") is not None and str(row.get("display_key")).strip()
            }
            if len(existing_keys) > 1:
                raise ValueError(
                    f"Conflicting existing display keys for {group_key}: {sorted(existing_keys)}"
                )
            if existing_keys:
                group_key_by_group[group_key] = next(iter(existing_keys))
                preserved_groups += 1
            else:
                borough, display_name = group_key
                group_key_by_group[group_key] = generate_display_key(market, borough, display_name)
                new_groups += 1

        session.execute(
            text(
                """
                UPDATE region_boundaries
                SET display_name = :display_name,
                    display_order = :display_order,
                    display_key = CASE
                        WHEN :display_name IS NULL THEN NULL
                        ELSE COALESCE(display_key, :generated_key)
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            [
                {
                    "id": str(row["id"]),
                    "display_name": row["mapped_display_name"],
                    "display_order": (
                        display_order_by_group[(str(row["parent_region"]), str(row["mapped_display_name"]))]
                        if row["mapped_display_name"] is not None
                        else None
                    ),
                    "generated_key": (
                        group_key_by_group[(str(row["parent_region"]), str(row["mapped_display_name"]))]
                        if row["mapped_display_name"] is not None
                        else None
                    ),
                }
                for row in rows
            ],
        )
        session.commit()

    stats = {
        "total_rows": len(rows),
        "mapped_count": mapped_count,
        "dropped_count": dropped_count,
        "unique_display_names": sum(len(names) for names in display_names_by_borough.values()),
        "unique_keys": len(group_key_by_group),
        "preserved_keys": preserved_groups,
        "new_keys": new_groups,
    }

    if verbose:
        print(
            "Neighborhood display seed complete: "
            f"mapped={stats['mapped_count']} "
            f"dropped={stats['dropped_count']} "
            f"unique_display_names={stats['unique_display_names']} "
            f"unique_keys={stats['unique_keys']}"
        )
        print(
            f"Keys: {stats['unique_keys']} total "
            f"({stats['preserved_keys']} preserved, {stats['new_keys']} newly generated)"
        )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed neighborhood display columns.")
    parser.add_argument("--region-type", default="nyc")
    parser.add_argument("--market", default="nyc")
    parser.add_argument("--database-url", default=settings.get_database_url())
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    engine = create_engine(args.database_url)
    try:
        seed_neighborhood_display(
            engine,
            region_type=args.region_type,
            market=args.market,
            verbose=not args.quiet,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
