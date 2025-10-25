#!/usr/bin/env python3
"""
backfill_badges.py — thin CLI wrapper for BadgeAwardService.backfill_user_badges.

Default behavior is a dry run with notifications disabled. Use --no-dry-run to
persist awards and --send-notifications to fire immediate badge notifications.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.render", override=False)
except Exception:  # pragma: no cover - dotenv is optional in tests
    pass

from app.database import SessionLocal
from app.repositories.factory import RepositoryFactory
from app.repositories.user_repository import UserRepository
from app.services.badge_award_service import BadgeAwardService

SUMMARY_FIELDS = ("milestones", "streak", "explorer", "quality_pending", "skipped_existing")
logger = logging.getLogger("backfill_badges")


def _positive_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected integer, got {value!r}") from exc
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero")
    return ivalue


def _non_negative_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected integer, got {value!r}") from exc
    if ivalue < 0:
        raise argparse.ArgumentTypeError("Value must be zero or greater")
    return ivalue


def _iso8601(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO-8601 datetime: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recompute badge eligibility for batches of students.")
    parser.add_argument("--limit", type=_positive_int, default=1000, help="Rows per chunk (default: 1000)")
    parser.add_argument("--offset", type=_non_negative_int, default=0, help="Starting offset (default: 0)")
    parser.add_argument(
        "--since",
        type=_iso8601,
        default=None,
        help="Optional ISO datetime to start from (filters by user.created_at).",
    )
    parser.add_argument(
        "--quality-window-days",
        type=_positive_int,
        default=90,
        help="Review window for quality badge calculations (default: 90).",
    )
    dry_group = parser.add_mutually_exclusive_group()
    dry_group.add_argument("--dry-run", dest="dry_run", action="store_true", help="Force dry-run mode.")
    dry_group.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Persist awards (disables dry-run safeguards).",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--send-notifications",
        dest="send_notifications",
        action="store_true",
        default=False,
        help="Send notifications for instant awards.",
    )
    parser.add_argument("--user-id", dest="user_id", help="Process a single student (skip pagination).")
    parser.add_argument(
        "--max-users",
        dest="max_users",
        type=_positive_int,
        default=None,
        help="Optional hard cap on processed users.",
    )
    return parser


def _init_summary(dry_run: bool, send_notifications: bool) -> Dict[str, Any]:
    summary: Dict[str, Any] = {field: 0 for field in SUMMARY_FIELDS}
    summary["processed_users"] = 0
    summary["dry_run"] = dry_run
    summary["send_notifications"] = send_notifications
    return summary


def _process_users_chunk(
    students: Iterable[Any],
    *,
    chunk_index: int,
    chunk_offset: int,
    summary: Dict[str, Any],
    badge_service: BadgeAwardService,
    args,
) -> Dict[str, int]:
    chunk_totals: Dict[str, int] = {field: 0 for field in SUMMARY_FIELDS}
    chunk_totals["processed_users"] = 0

    for student in students:
        student_id = getattr(student, "id", None)
        if not student_id:
            continue
        try:
            result = badge_service.backfill_user_badges(
                student_id,
                datetime.now(timezone.utc),
                quality_window_days=args.quality_window_days,
                send_notifications=args.send_notifications,
                dry_run=args.dry_run,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to backfill user %s: %s", student_id, exc)
            continue
        result = result or {}

        chunk_totals["processed_users"] += 1
        summary["processed_users"] += 1
        for field in SUMMARY_FIELDS:
            value = int(result.get(field, 0) or 0)
            chunk_totals[field] += value
            summary[field] += value

    payload = {"chunk": chunk_index, "offset": chunk_offset, **chunk_totals}
    print(f"[chunk] {json.dumps(payload)}")
    return chunk_totals


def _process_single_user(
    *,
    user_repo: UserRepository,
    badge_service: BadgeAwardService,
    session,
    args,
) -> Dict[str, Any]:
    summary = _init_summary(args.dry_run, args.send_notifications)
    student = user_repo.get_by_id(args.user_id)
    if not student:
        raise ValueError(f"User {args.user_id} not found")

    _process_users_chunk(
        [student],
        chunk_index=1,
        chunk_offset=0,
        summary=summary,
        badge_service=badge_service,
        args=args,
    )
    if not args.dry_run:
        # repo-pattern-migrate: TODO: migrate to repository (unit-of-work/commit)
        session.commit()
    return summary


def _process_batches(
    *,
    user_repo: UserRepository,
    badge_service: BadgeAwardService,
    session,
    args,
) -> Dict[str, Any]:
    summary = _init_summary(args.dry_run, args.send_notifications)
    current_offset = args.offset
    remaining_cap = args.max_users
    chunk_index = 1

    while True:
        chunk_limit = args.limit
        if remaining_cap is not None:
            chunk_limit = min(chunk_limit, remaining_cap)
            if chunk_limit <= 0:
                break

        students: List[Any] = user_repo.list_students_paginated(
            limit=chunk_limit,
            offset=current_offset,
            since=args.since,
        )
        if not students:
            break

        _process_users_chunk(
            students,
            chunk_index=chunk_index,
            chunk_offset=current_offset,
            summary=summary,
            badge_service=badge_service,
            args=args,
        )

        if not args.dry_run:
            # repo-pattern-migrate: TODO: migrate to repository (unit-of-work/commit)
            session.commit()

        processed = len(students)
        current_offset += processed
        chunk_index += 1
        if remaining_cap is not None:
            remaining_cap -= processed
            if remaining_cap <= 0:
                break

    return summary


def run(args) -> Dict[str, Any]:
    session = SessionLocal()
    try:
        user_repo = RepositoryFactory.create_user_repository(session)
        badge_service = BadgeAwardService(session)

        if args.user_id:
            summary = _process_single_user(
                user_repo=user_repo,
                badge_service=badge_service,
                session=session,
                args=args,
            )
        else:
            summary = _process_batches(
                user_repo=user_repo,
                badge_service=badge_service,
                session=session,
                args=args,
            )
    finally:
        session.close()
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        summary = run(args)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Badge backfill failed: %s", exc)
        return 1

    print(json.dumps(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
