#!/usr/bin/env python
"""
Utility script to clear Redis cache via the platform's CacheService.

Usage:
  python backend/scripts/clear_cache.py                 # Clears all common patterns
  python backend/scripts/clear_cache.py --scope catalog # Clears catalog/search-only patterns

This script respects REDIS_URL and other backend settings via app.core.config.
"""

import argparse
import os
from pathlib import Path
import sys

# Ensure backend is on sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_db
from app.services.cache_service import CacheService
from app.utils.env_logging import log_info, log_warn

_ENV_ALIASES = {
    "prod": {"prod", "production", "live"},
    "preview": {"preview", "pre"},
    "stg": {"stg", "stage", "staging", "local"},
    "int": {"int", "dev", "development", "ci", "test"},
}


def _resolve_env() -> str:
    site_mode = (os.getenv("SITE_MODE") or "").strip().lower()
    if site_mode:
        for canon, aliases in _ENV_ALIASES.items():
            if site_mode in aliases:
                return canon
    return "int"


def clear_patterns(cache_service: CacheService, patterns: list[str], env: str) -> int:
    total = 0
    for pattern in patterns:
        try:
            count = cache_service.delete_pattern(pattern) or 0
            total += count
            log_info(env, f"Cleared {count} keys matching '{pattern}'")
        except Exception as e:
            log_warn(env, f"Could not clear pattern '{pattern}': {e}")
    return total


def main():
    parser = argparse.ArgumentParser(description="Clear Redis cache patterns")
    parser.add_argument(
        "--scope",
        choices=["all", "catalog"],
        default="all",
        help="Limit which patterns to clear",
    )
    parser.add_argument(
        "--echo-sentinel",
        action="store_true",
        help="Print CACHE_CLEAR_OK when clearing completes",
    )
    args = parser.parse_args()

    env = _resolve_env()
    log_info(env, f"Clearing cache (scope={args.scope})…")

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

        total = clear_patterns(cache_service, patterns, env)
        log_info(env, f"Total cache keys cleared: {total}")
        if args.echo_sentinel:
            print("CACHE_CLEAR_OK")
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
