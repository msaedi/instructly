#!/usr/bin/env python3
"""
CLI utility to generate a beta invite code without sending email.

Usage example:
  python backend/scripts/generate_beta_invite_code.py \
      --role instructor_beta --days 14 --source cli --email test@example.com
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import List, Optional

# Ensure staging mode is selected before importing application settings
os.environ.setdefault("SITE_MODE", "stg")

# Make backend package importable when running from repo root
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.beta_service import BetaService, build_join_url, build_welcome_url


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a beta invite code")
    parser.add_argument("--email", default=None, help="Optional email to associate with the invite")
    parser.add_argument(
        "--role",
        default="instructor_beta",
        help="Role to grant when the invite is used (default: instructor_beta)",
    )
    parser.add_argument("--days", type=int, default=14, help="Expiry in days (default: 14)")
    parser.add_argument(
        "--source",
        default="cli",
        help="Source metadata tag stored with the invite (default: cli)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Optional override for the frontend base URL used in generated links",
    )

    args = parser.parse_args(argv)

    db: Session = SessionLocal()
    try:
        service = BetaService(db)
        emails = [args.email] if args.email else None
        invites = service.bulk_generate(
            count=1,
            role=args.role,
            expires_in_days=args.days,
            source=args.source,
            emails=emails,
        )
        db.commit()

        invite = invites[0]
        join_url = build_join_url(invite.code, args.email, args.base)
        welcome_url = build_welcome_url(invite.code, args.email, args.base)

        print("Invite generated:")
        print(f"  Code: {invite.code}")
        if args.email:
            print(f"  Email: {args.email}")
        print(f"  Role: {invite.role}")
        if invite.expires_at is not None:
            print(f"  Expires At: {invite.expires_at.isoformat()}")
        else:
            print("  Expires At: never")
        print(f"  Join URL: {join_url}")
        print(f"  Welcome URL: {welcome_url}")
        print("\nNote: SITE_MODE=stg applied automatically; export SITE_MODE beforehand to override.")
        return 0
    except Exception as exc:  # noqa: BLE001 keep CLI failure simple
        db.rollback()
        print(f"Failed to generate invite: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
