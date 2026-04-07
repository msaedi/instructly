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

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "location_aliases.json"
DEFAULT_CITY_ID = "01JDEFAULTNYC0000000000"

# Ensure `app/` is importable when called directly.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.ulid_helper import generate_ulid  # noqa: E402


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

    Returns the number of INSERT/UPSERT attempts (best-effort; idempotent via ON CONFLICT).
    """
    payload = _load_aliases(data_path)
    aliases = payload.get("aliases") or []
    ambiguous_aliases = payload.get("ambiguous_aliases") or []
    if not isinstance(aliases, list) or not isinstance(ambiguous_aliases, list):
        raise ValueError(
            "Invalid location_aliases.json: 'aliases' and 'ambiguous_aliases' must be lists"
        )

    inserted = 0
    skipped_duplicate = 0
    missing_region = 0
    skipped_existing = 0
    insert_errors = 0
    inserted_new = 0
    updated_existing = 0

    with Session(engine) as session:
        is_postgres = session.bind is not None and session.bind.dialect.name == "postgresql"

        city_id = str(payload.get("city_id") or DEFAULT_CITY_ID).strip()
        existing_aliases = {
            _normalize(str(row[0]))
            for row in session.execute(
                text(
                    """
                    SELECT alias_normalized
                    FROM location_aliases
                    WHERE city_id = :city_id
                    """
                ),
                {"city_id": city_id},
            ).fetchall()
            if row and row[0]
        }

        rows = session.execute(
            text(
                """
                SELECT id, region_name, display_name, display_key
                FROM region_boundaries
                WHERE region_type = :rtype
                  AND region_name IS NOT NULL
                """
            ),
            {"rtype": region_code},
        ).fetchall()
        name_to_rows: dict[str, list[dict[str, str | None]]] = {}
        for row in rows:
            if not row[1]:
                continue
            region_name = str(row[1]).strip()
            normalized_name = _normalize(region_name)
            name_to_rows.setdefault(normalized_name, []).append(
                {
                    "id": str(row[0]),
                    "region_name": region_name,
                    "display_name": str(row[2]).strip() if row[2] else None,
                    "display_key": str(row[3]).strip() if row[3] else None,
                }
            )

        def _region_sort_key(region_row: dict[str, str | None]) -> tuple[str, str]:
            return (
                _normalize(str(region_row.get("region_name") or "")),
                str(region_row.get("id") or ""),
            )

        def _dedupe_region_rows(
            region_rows: list[dict[str, str | None]],
        ) -> list[dict[str, str | None]]:
            deduped: list[dict[str, str | None]] = []
            seen_region_ids: set[str] = set()
            for region_row in sorted(region_rows, key=_region_sort_key):
                region_id = str(region_row.get("id") or "")
                if not region_id or region_id in seen_region_ids:
                    continue
                seen_region_ids.add(region_id)
                deduped.append(region_row)
            return deduped

        def _find_region_rows(region_name: str) -> list[dict[str, str | None]]:
            key = _normalize(region_name)
            exact_rows = name_to_rows.get(key)
            if exact_rows:
                return _dedupe_region_rows(list(exact_rows))
            # Best-effort normalization (e.g., "Astoria (Central)" -> "Astoria").
            candidates: list[dict[str, str | None]] = []
            for existing_name, matched_rows in name_to_rows.items():
                if key in existing_name or existing_name in key:
                    candidates.extend(matched_rows)
            return _dedupe_region_rows(candidates)

        def _logical_group_key(region_row: dict[str, str | None]) -> str:
            display_key = str(region_row.get("display_key") or "").strip()
            if display_key:
                return f"display:{display_key}"
            return f"region:{str(region_row.get('id') or '').strip()}"

        def _logical_group_label(region_row: dict[str, str | None]) -> str:
            return _normalize(
                str(region_row.get("display_name") or region_row.get("region_name") or "")
            )

        def _group_region_rows(
            region_rows: list[dict[str, str | None]],
        ) -> list[list[dict[str, str | None]]]:
            grouped: dict[str, list[dict[str, str | None]]] = {}
            for region_row in _dedupe_region_rows(region_rows):
                grouped.setdefault(_logical_group_key(region_row), []).append(region_row)
            return [grouped[key] for key in sorted(grouped)]

        def _pick_resolved_group(
            region_name: str,
            region_rows: list[dict[str, str | None]],
        ) -> list[dict[str, str | None]] | None:
            grouped_rows = _group_region_rows(region_rows)
            if not grouped_rows:
                return None
            if len(grouped_rows) == 1:
                return grouped_rows[0]

            target_label = _normalize(region_name)
            exact_matches: list[list[dict[str, str | None]]] = []
            for group_rows in grouped_rows:
                labels = {
                    _logical_group_label(region_row)
                    for region_row in group_rows
                    if _logical_group_label(region_row)
                }
                if target_label and target_label in labels:
                    exact_matches.append(group_rows)
            if len(exact_matches) == 1:
                return exact_matches[0]
            return None

        seen_aliases: set[str] = set()

        def _insert_resolved_alias(
            *,
            alias_normalized: str,
            region_boundary_id: str,
            candidate_region_ids: list[str] | None,
            alias_type: str,
            confidence: float,
        ) -> None:
            nonlocal inserted, inserted_new, updated_existing, skipped_existing, insert_errors
            try:
                existed = alias_normalized in existing_aliases
                candidate_value: Any = None
                if candidate_region_ids:
                    candidate_value = (
                        candidate_region_ids if is_postgres else json.dumps(candidate_region_ids)
                    )
                result = session.execute(
                    text(
                        """
                        INSERT INTO location_aliases (
                            id,
                            city_id,
                            alias_normalized,
                            region_boundary_id,
                            requires_clarification,
                            candidate_region_ids,
                            status,
                            confidence,
                            source,
                            user_count,
                            alias_type
                        )
                        VALUES (
                            :id,
                            :city_id,
                            :alias_normalized,
                            :region_boundary_id,
                            FALSE,
                            :candidate_region_ids,
                            'active',
                            :confidence,
                            'manual',
                            1,
                            :alias_type
                        )
                        ON CONFLICT (city_id, alias_normalized) DO UPDATE SET
                            region_boundary_id = EXCLUDED.region_boundary_id,
                            requires_clarification = FALSE,
                            candidate_region_ids = EXCLUDED.candidate_region_ids,
                            status = 'active',
                            confidence = EXCLUDED.confidence,
                            source = 'manual',
                            alias_type = EXCLUDED.alias_type,
                            updated_at = CURRENT_TIMESTAMP,
                            deprecated_at = NULL
                        """
                    ),
                    {
                        "id": generate_ulid(),
                        "city_id": city_id,
                        "alias_normalized": alias_normalized,
                        "region_boundary_id": region_boundary_id,
                        "candidate_region_ids": candidate_value,
                        "confidence": float(confidence),
                        "alias_type": alias_type,
                    },
                )
                if getattr(result, "rowcount", 0) == 1:
                    inserted += 1
                    if existed:
                        updated_existing += 1
                    else:
                        inserted_new += 1
                        existing_aliases.add(alias_normalized)
                    if verbose and alias_normalized == "ues":
                        action = "Updated" if existed else "Inserted"
                        print(
                            f"  ✓ {action} '{alias_normalized}' -> resolved ({region_boundary_id})"
                        )
                else:
                    skipped_existing += 1
            except Exception as e:
                insert_errors += 1
                if verbose:
                    print(f"  ⚠ Could not insert alias '{alias_normalized}': {e}")

        def _insert_ambiguous_alias(*, alias_normalized: str, candidate_region_ids: list[str], alias_type: str, confidence: float) -> None:
            nonlocal inserted, inserted_new, updated_existing, skipped_existing, insert_errors
            try:
                existed = alias_normalized in existing_aliases
                candidate_value: Any = candidate_region_ids if is_postgres else json.dumps(candidate_region_ids)
                result = session.execute(
                    text(
                        """
                        INSERT INTO location_aliases (
                            id,
                            city_id,
                            alias_normalized,
                            region_boundary_id,
                            requires_clarification,
                            candidate_region_ids,
                            status,
                            confidence,
                            source,
                            user_count,
                            alias_type
                        )
                        VALUES (
                            :id,
                            :city_id,
                            :alias_normalized,
                            NULL,
                            TRUE,
                            :candidate_region_ids,
                            'active',
                            :confidence,
                            'manual',
                            1,
                            :alias_type
                        )
                        ON CONFLICT (city_id, alias_normalized) DO UPDATE SET
                            region_boundary_id = NULL,
                            requires_clarification = TRUE,
                            candidate_region_ids = EXCLUDED.candidate_region_ids,
                            status = 'active',
                            confidence = EXCLUDED.confidence,
                            source = 'manual',
                            alias_type = EXCLUDED.alias_type,
                            updated_at = CURRENT_TIMESTAMP,
                            deprecated_at = NULL
                        """
                    ),
                    {
                        "id": generate_ulid(),
                        "city_id": city_id,
                        "alias_normalized": alias_normalized,
                        "candidate_region_ids": candidate_value,
                        "confidence": float(confidence),
                        "alias_type": alias_type,
                    },
                )
                if getattr(result, "rowcount", 0) == 1:
                    inserted += 1
                    if existed:
                        updated_existing += 1
                    else:
                        inserted_new += 1
                        existing_aliases.add(alias_normalized)
                    if verbose and alias_normalized == "ues":
                        action = "Updated" if existed else "Inserted"
                        print(
                            f"  ✓ {action} '{alias_normalized}' -> ambiguous ({len(candidate_region_ids)} candidates)"
                        )
                else:
                    skipped_existing += 1
            except Exception as e:
                insert_errors += 1
                if verbose:
                    print(f"  ⚠ Could not insert ambiguous alias '{alias_normalized}': {e}")

        for row in aliases:
            if not isinstance(row, dict):
                continue

            alias = _normalize(row.get("alias", ""))
            region_name = str(row.get("region_name", "")).strip()
            alias_type = str(row.get("type") or row.get("alias_type") or "abbreviation").strip().lower()
            confidence = float(row.get("confidence") or 1.0)

            if not alias or not region_name:
                continue

            if alias in seen_aliases:
                skipped_duplicate += 1
                continue
            seen_aliases.add(alias)

            matched_rows = _find_region_rows(region_name)
            if not matched_rows:
                missing_region += 1
                if verbose:
                    print(f"  ⚠ Region not found for alias '{alias}': '{region_name}'")
                continue

            resolved_group = _pick_resolved_group(region_name, matched_rows)
            if resolved_group is not None:
                sorted_group = sorted(_dedupe_region_rows(resolved_group), key=_region_sort_key)
                primary_region_id = str(sorted_group[0].get("id") or "")
                supporting_region_ids = [
                    str(region_row.get("id") or "") for region_row in sorted_group[1:]
                ]
                _insert_resolved_alias(
                    alias_normalized=alias,
                    region_boundary_id=primary_region_id,
                    candidate_region_ids=supporting_region_ids or None,
                    alias_type=alias_type,
                    confidence=confidence,
                )
            else:
                # Coarse labels that span multiple logical display groups stay ambiguous.
                _insert_ambiguous_alias(
                    alias_normalized=alias,
                    candidate_region_ids=[
                        str(region_row.get("id") or "") for region_row in matched_rows
                    ],
                    alias_type=alias_type,
                    confidence=confidence,
                )

        for row in ambiguous_aliases:
            if not isinstance(row, dict):
                continue

            alias = _normalize(row.get("alias", ""))
            candidate_names = row.get("candidates") or []
            alias_type = str(row.get("type") or row.get("alias_type") or "colloquial").strip().lower()
            confidence = float(row.get("confidence") or 1.0)

            if not alias or not isinstance(candidate_names, list):
                continue

            if alias in seen_aliases:
                skipped_duplicate += 1
                continue
            seen_aliases.add(alias)

            candidate_ids: list[str] = []
            for name in candidate_names:
                if not name:
                    continue
                matched_rows = _find_region_rows(str(name))
                if matched_rows:
                    candidate_ids.extend(
                        str(region_row.get("id") or "") for region_row in matched_rows
                    )
                elif verbose:
                    print(f"  ⚠ Candidate not found for ambiguous alias '{alias}': '{name}'")

            candidate_ids = list(dict.fromkeys(candidate_ids))
            if len(candidate_ids) < 2:
                missing_region += 1
                if verbose:
                    print(f"  ⚠ Not enough candidates found for ambiguous alias '{alias}', skipping")
                continue

            _insert_ambiguous_alias(
                alias_normalized=alias,
                candidate_region_ids=candidate_ids,
                alias_type=alias_type,
                confidence=confidence,
            )

        session.commit()

    if verbose:
        print(f"  ✓ Seeded {inserted} location aliases ({region_code})")
        if skipped_duplicate:
            print(f"    - Skipped duplicates in JSON: {skipped_duplicate}")
        if inserted_new or updated_existing:
            print(f"    - Inserted new: {inserted_new}")
            print(f"    - Updated existing: {updated_existing}")
        if skipped_existing:
            print(f"    - Skipped (already exists): {skipped_existing}")
        if missing_region:
            print(f"    - Skipped (missing region_boundaries row/candidates): {missing_region}")
        if insert_errors:
            print(f"    - Skipped (insert errors): {insert_errors}")

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
