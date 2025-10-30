#!/usr/bin/env python3
# backend/scripts/retention/purge_soft_deleted.py
"""
CLI wrapper around RetentionService.purge_soft_deleted.

Usage:
    python scripts/retention/purge_soft_deleted.py --days 45 --chunk 500
    python scripts/retention/purge_soft_deleted.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:  # pragma: no cover - optional for tests
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.render", override=False)
except Exception:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:  # type: ignore
        return False

from app.database import SessionLocal
from app.services.cache_service import CacheService
from app.services.retention_service import RetentionService

logger = logging.getLogger("retention.purge")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected integer, got {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Permanently delete soft-deleted rows older than the retention window."
    )
    parser.add_argument(
        "--days",
        type=_positive_int,
        default=30,
        help="Soft-deleted rows older than this many days will be purged (default: 30).",
    )
    parser.add_argument(
        "--chunk",
        type=_positive_int,
        default=1000,
        help="Maximum rows to delete per transaction (default: 1000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report counts, do not delete anything.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of formatted text.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("RETENTION_LOG_LEVEL", "INFO"),
        help="Override log level (default: INFO).",
    )
    return parser


def _format_summary(summary: Dict[str, Dict[str, Any]]) -> str:
    lines = []
    meta = summary.get("_meta", {})
    header = f"Retention summary — cutoff={meta.get('cutoff')} (chunk={meta.get('chunk_size')})"
    if meta.get("dry_run"):
        header += " [DRY-RUN]"
    lines.append(header)

    for table, stats in summary.items():
        if table == "_meta":
            continue
        eligible = stats.get("eligible", 0)
        deleted = stats.get("deleted", 0)
        chunks = stats.get("chunks", 0)
        lines.append(f"  - {table}: eligible={eligible} deleted={deleted} chunks={chunks}")
    if len(lines) == 1:
        lines.append("  (no configured tables matched)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    session = SessionLocal()
    cache_service = CacheService(session)
    retention_service = RetentionService(session, cache_service=cache_service)

    try:
        summary = retention_service.purge_soft_deleted(
            older_than_days=args.days,
            chunk_size=args.chunk,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # pragma: no cover - CLI guardrail
        logger.exception("Retention purge failed: %s", exc)
        return 1
    finally:
        session.close()

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(_format_summary(summary))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
