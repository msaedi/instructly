#!/usr/bin/env python3
"""
Populate `region_boundaries.name_embedding` for semantic location resolution (Tier 4).

Uses OpenAI `text-embedding-3-small` (1536 dims by default) to embed region names.

Usage:
  python backend/scripts/populate_region_embeddings.py --region-type nyc

Environment:
  - OPENAI_API_KEY (required)
  - OPENAI_EMBEDDING_MODEL (optional, default: text-embedding-3-small)
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure `app/` is importable when called directly.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402

logger = logging.getLogger(__name__)


def _embedding_text(region_name: str, parent_region: str | None, region_type: str) -> str:
    """Build a rich embedding input for a region boundary."""
    base = region_name.strip()
    parts = [base]
    if parent_region:
        parts.append(str(parent_region).strip())
    # Provide lightweight disambiguation/context.
    parts.append(f"{region_type.upper()} location")
    return ", ".join([p for p in parts if p])


def populate_region_embeddings(
    *,
    region_type: str,
    batch_size: int = 50,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY environment variable required")

    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    client = OpenAI(api_key=api_key)

    db_url = settings.database_url
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        if force:
            query = text(
                """
                SELECT id, region_name, parent_region
                FROM region_boundaries
                WHERE region_type = :rtype
                  AND region_name IS NOT NULL
                ORDER BY region_name
                """
            )
        else:
            query = text(
                """
                SELECT id, region_name, parent_region
                FROM region_boundaries
                WHERE region_type = :rtype
                  AND region_name IS NOT NULL
                  AND name_embedding IS NULL
                ORDER BY region_name
                """
            )

        rows = db.execute(query, {"rtype": region_type}).fetchall()
        regions: List[Dict[str, Any]] = [
            {
                "id": str(r.id),
                "region_name": str(r.region_name),
                "parent_region": str(r.parent_region) if r.parent_region else None,
            }
            for r in rows
        ]

        if not regions:
            logger.info("No region_boundaries rows need embeddings (region_type=%s).", region_type)
            return

        logger.info(
            "Found %d region_boundaries rows to embed (region_type=%s, model=%s).",
            len(regions),
            region_type,
            model,
        )

        if dry_run:
            for region in regions[:10]:
                logger.info("  - %s", region["region_name"])
            if len(regions) > 10:
                logger.info("  ... and %d more", len(regions) - 10)
            return

        updated = 0
        for i in range(0, len(regions), batch_size):
            batch = regions[i : i + batch_size]
            inputs = [
                _embedding_text(r["region_name"], r["parent_region"], region_type) for r in batch
            ]

            start = time.time()
            response = client.embeddings.create(model=model, input=inputs)
            latency_ms = int((time.time() - start) * 1000)

            for j, item in enumerate(response.data):
                region_id = batch[j]["id"]
                embedding = list(item.embedding)
                db.execute(
                    text(
                        """
                        UPDATE region_boundaries
                        SET name_embedding = :embedding,
                            updated_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    {"id": region_id, "embedding": embedding},
                )

            db.commit()
            updated += len(batch)
            logger.info(
                "Embedded %d/%d regions (batch=%d, latency=%dms)",
                updated,
                len(regions),
                len(batch),
                latency_ms,
            )

            # Small delay to be polite to API rate limits.
            if i + batch_size < len(regions):
                time.sleep(0.25)

        logger.info("Done. Embedded %d regions.", updated)
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Populate region_boundaries.name_embedding.")
    parser.add_argument("--region-type", default="nyc", help="Region type (default: nyc)")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size (default: 50)")
    parser.add_argument("--force", action="store_true", help="Re-embed even if already present")
    parser.add_argument("--dry-run", action="store_true", help="Print sample rows and exit")
    args = parser.parse_args()

    populate_region_embeddings(
        region_type=str(args.region_type).strip().lower(),
        batch_size=int(args.batch_size),
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
