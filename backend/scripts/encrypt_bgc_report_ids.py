#!/usr/bin/env python3
"""Backfill utility to encrypt background-check report identifiers in place."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Iterable, Optional

os.environ.setdefault("SITE_MODE", "stg")

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy.orm import Session

from app.core.crypto import assert_encryption_ready, decrypt_report_token
from app.core.metrics import BGC_REPORT_ID_DECRYPT_TOTAL
from app.database import SessionLocal
from app.models.instructor import InstructorProfile
from app.repositories.instructor_profile_repository import InstructorProfileRepository

logger = logging.getLogger("encrypt_bgc_report_ids")


def _classify_report(raw_value: str | None) -> tuple[str, str | None]:
    """Classify stored report identifiers as encrypted or plaintext."""

    if raw_value in (None, ""):
        return "empty", raw_value

    if raw_value.startswith("v1:"):
        try:
            decrypted = decrypt_report_token(raw_value)
        except ValueError:
            return "error", raw_value
        BGC_REPORT_ID_DECRYPT_TOTAL.inc()
        return "encrypted", decrypted

    return "plaintext", raw_value


def _iter_candidates(session: Session, *, limit: Optional[int]) -> Iterable[InstructorProfile]:
    query = (
        session.query(InstructorProfile)
        .filter(InstructorProfile._bgc_report_id.isnot(None))  # type: ignore[attr-defined]
        .order_by(InstructorProfile.created_at.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.yield_per(100)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Encrypt plaintext bgc_report_id values")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to scan (default: all)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist changes; otherwise runs in dry-run mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly run without committing (default)",
    )

    args = parser.parse_args(argv)
    dry_run = not args.commit or args.dry_run

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        assert_encryption_ready()
    except RuntimeError as exc:  # noqa: BLE001 - surface startup guard clearly
        logger.error("%s", exc)
        return 1

    session: Session = SessionLocal()
    repository = InstructorProfileRepository(session)

    scanned = encrypted = skipped = errors = 0

    try:
        for profile in _iter_candidates(session, limit=args.limit):
            scanned += 1
            raw_value = getattr(profile, "_bgc_report_id", None)
            status, plain = _classify_report(raw_value)

            if status == "error":
                errors += 1
                logger.error(
                    "Unable to decrypt candidate report id for instructor %s; skipping",
                    profile.id,
                )
                continue

            if status == "encrypted":
                skipped += 1
                continue

            if status == "empty" or plain in (None, ""):
                skipped += 1
                continue

            if dry_run:
                encrypted += 1
                logger.info(
                    "[dry-run] would encrypt report id for instructor %s", profile.id
                )
                continue

            try:
                encrypted_value = repository._encrypt_report_id(plain, source="backfill")
                setattr(profile, "_bgc_report_id", encrypted_value)
                encrypted += 1
                logger.info("Encrypted report id for instructor %s", profile.id)
            except Exception as exc:  # noqa: BLE001 - continue processing
                errors += 1
                logger.exception(
                    "Failed to encrypt report id for instructor %s: %s",
                    profile.id,
                    exc,
                )

        if dry_run:
            session.rollback()
        else:
            session.commit()
    finally:
        session.close()

    logger.info(
        "Backfill complete: scanned=%s encrypted=%s skipped=%s errors=%s dry_run=%s",
        scanned,
        encrypted,
        skipped,
        errors,
        dry_run,
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
