#!/usr/bin/env python3
"""
Directly test Tier 5 LLM location resolution with a generous timeout.

Usage:
  python backend/scripts/test_location_llm.py --query "american natural history museum"
  python backend/scripts/test_location_llm.py --query "natural history museum" --timeout-s 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
from typing import List

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import get_db_session
from app.repositories.search_batch_repository import SearchBatchRepository
from app.services.search.location_llm_service import LocationLLMService


def _load_region_names(region_code: str) -> List[str]:
    with get_db_session() as db:
        repo = SearchBatchRepository(db, region_code=region_code)
        lookup = repo.load_region_lookup()
    return list(lookup.region_names)


async def _run(query: str, *, timeout_s: float, region_code: str) -> None:
    candidates = _load_region_names(region_code)
    candidate_lower = {c.lower() for c in candidates}
    service = LocationLLMService()

    result, debug = await service.resolve_with_debug(
        location_text=query,
        allowed_region_names=candidates,
        timeout_s=timeout_s,
    )

    print("\n=== Tier 5 LLM Debug ===")
    print(f"Query: {query}")
    print(f"Region code: {region_code}")
    print(f"Timeout: {timeout_s:.2f}s")
    print(f"Candidates: {len(candidates)} total")
    print(f"Contains 'Upper West Side': {'upper west side' in candidate_lower}")
    print("\n--- Prompt ---")
    print(debug.get("prompt") or "<none>")
    print("\n--- Raw Response ---")
    print(debug.get("raw_response") or "<none>")
    print("\n--- Parsed ---")
    print(json.dumps(result, indent=2))
    print("\n--- Debug Info ---")
    print(json.dumps(debug, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct LLM location resolver test")
    parser.add_argument(
        "--query",
        required=True,
        help="Location query to resolve",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=10.0,
        help="Timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--region-code",
        default="nyc",
        help="Region code (default: nyc)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(_run(args.query, timeout_s=args.timeout_s, region_code=args.region_code))


if __name__ == "__main__":
    main()
