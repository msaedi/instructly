#!/usr/bin/env python3
"""
Warm NL search caches with a curated list of popular queries.

This script runs NLSearchService end-to-end (parsing → retrieval → filtering → ranking)
so the response cache is populated for common queries.

Usage:
  python backend/scripts/seed_popular_queries.py --region nyc --limit 20

Notes:
  - Requires Redis configured for cache warming to persist across processes.
  - Requires OPENAI_API_KEY if EMBEDDING_PROVIDER=openai and embeddings are needed.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


POPULAR_QUERIES: list[str] = [
    # Instruments
    "piano lessons",
    "guitar lessons",
    "violin lessons",
    "drum lessons",
    "voice lessons",
    "singing lessons",
    # Locations (aliases and full names)
    "piano in upper east side",
    "piano in ues",
    "guitar in brooklyn",
    "piano in manhattan",
    "music lessons in nyc",
    # Audience
    "piano lessons for kids",
    "guitar lessons for beginners",
    "music lessons for adults",
    "piano for children",
    # Price intent
    "cheap piano lessons",
    "affordable guitar lessons",
    "piano lessons under 100",
    # Combined constraints
    "piano lessons for kids in ues",
    "guitar lessons in brooklyn for beginners",
    "violin lessons upper west side",
    # Other categories
    "math tutoring",
    "sat prep",
    "spanish lessons",
    "yoga classes",
    "swimming lessons",
    "tennis lessons",
]


async def warm_queries(
    *,
    db: Session,
    region_code: str,
    limit: int,
    user_location: Optional[tuple[float, float]],
) -> dict[str, int]:
    from app.services.cache_service import get_cache_service
    from app.services.search.nl_search_service import NLSearchService

    cache_service = get_cache_service(db)
    search_service = NLSearchService(db, cache_service=cache_service, region_code=region_code)

    success = 0
    failed = 0
    degraded = 0

    for idx, query in enumerate(POPULAR_QUERIES, start=1):
        try:
            result = await search_service.search(
                query=query,
                user_location=user_location,
                limit=limit,
            )
            if getattr(result.meta, "degraded", False):
                degraded += 1
            success += 1
            print(f"[{idx}/{len(POPULAR_QUERIES)}] ✓ '{query}' → {result.meta.total_results} results")
        except Exception as exc:
            failed += 1
            print(f"[{idx}/{len(POPULAR_QUERIES)}] ✗ '{query}' → {exc}")

    return {"success": success, "failed": failed, "degraded": degraded}


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm NL search caches with popular queries")
    parser.add_argument("--database-url", dest="database_url", default=None)
    parser.add_argument("--region", dest="region", default="nyc")
    parser.add_argument("--limit", dest="limit", type=int, default=20)
    parser.add_argument("--lat", dest="lat", type=float, default=None)
    parser.add_argument("--lng", dest="lng", type=float, default=None)
    args = parser.parse_args()

    if (args.lat is None) ^ (args.lng is None):
        raise SystemExit("--lat and --lng must be provided together")

    user_location: Optional[tuple[float, float]] = None
    if args.lat is not None and args.lng is not None:
        user_location = (args.lng, args.lat)

    from app.core.config import settings

    db_url = args.database_url or settings.database_url
    if not db_url:
        raise SystemExit("No database URL configured (set DATABASE_URL or pass --database-url)")

    engine = create_engine(db_url)
    try:
        with Session(engine) as session:
            stats = asyncio.run(
                warm_queries(
                    db=session,
                    region_code=args.region,
                    limit=args.limit,
                    user_location=user_location,
                )
            )
            print(
                "Done: "
                f"success={stats['success']} failed={stats['failed']} degraded={stats['degraded']}"
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
