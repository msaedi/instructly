#!/usr/bin/env python3
"""
Simple CLI to generate and send a beta invite email using existing service logic.

Usage:
  python backend/scripts/beta_invite_send.py --email test@example.com --role instructor --days 14 --source cli --base http://localhost:3000

Notes:
  - Uses repository/service pattern via a DB session; no direct HTTP calls.
  - Prints the generated code and URLs for quick testing of the instructor join flow.
"""

from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.beta_service import BetaService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a beta invite email")
    parser.add_argument("--email", required=True, help="Recipient email")
    parser.add_argument("--role", default="instructor", help="Role to grant (default: instructor)")
    parser.add_argument("--days", type=int, default=14, help="Expiry in days (default: 14)")
    parser.add_argument("--source", default="cli", help="Source tag for metadata (default: cli)")
    parser.add_argument("--base", default=None, help="Frontend base URL override (default: settings.frontend_url)")

    args = parser.parse_args(argv)

    db: Session = SessionLocal()
    try:
        service = BetaService(db)
        invite, join_url, welcome_url = service.send_invite_email(
            to_email=args.email,
            role=args.role,
            expires_in_days=args.days,
            source=args.source,
            base_url=args.base,
        )
        print("Invite sent:")
        print(f"  Code: {invite.code}")
        print(f"  Join URL: {join_url}")
        print(f"  Welcome URL: {welcome_url}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
