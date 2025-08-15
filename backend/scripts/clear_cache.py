#!/usr/bin/env python
"""
Utility script to clear Redis cache via the platform's CacheService.

Usage:
  python backend/scripts/clear_cache.py                 # Clears all common patterns
  python backend/scripts/clear_cache.py --scope catalog # Clears catalog/search-only patterns

This script respects REDIS_URL and other backend settings via app.core.config.
"""

import argparse
import sys
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_db
from app.services.cache_service import CacheService


def clear_patterns(cache_service: CacheService, patterns: list[str]) -> int:
    total = 0
    for pattern in patterns:
        try:
            count = cache_service.delete_pattern(pattern)
            total += count
            print(f"✓ Cleared {count} keys matching '{pattern}'")
        except Exception as e:
            print(f"⚠ Could not clear pattern '{pattern}': {e}")
    return total


def main():
    parser = argparse.ArgumentParser(description="Clear Redis cache patterns")
    parser.add_argument(
        "--scope",
        choices=["all", "catalog"],
        default="all",
        help="Limit which patterns to clear",
    )
    args = parser.parse_args()

    # Acquire DB session and initialize cache service
    db = next(get_db())
    try:
        cache_service = CacheService(db)

        if args.scope == "catalog":
            patterns = [
                "catalog:*",
                "search:*",
                "public_availability:*",
            ]
        else:
            patterns = [
                "catalog:*",
                "search:*",
                "analytics:*",
                "instructor:*",
                "public_availability:*",
            ]

        print(f"Clearing cache (scope={args.scope})...")
        total = clear_patterns(cache_service, patterns)
        print(f"Total cache keys cleared: {total}")
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
