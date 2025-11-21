#!/usr/bin/env python3
"""Send background-check email templates to a target address for manual review."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, Dict, Optional

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ENV_FILE = BASE_DIR / ".env"


if TYPE_CHECKING:
    from app.services.template_registry import TemplateRegistry


def _ensure_env(env_file: Optional[str]) -> Path:
    """Load environment variables from the provided env file (default: backend/.env)."""

    if env_file:
        explicit = Path(env_file).expanduser().resolve()
    else:
        explicit = DEFAULT_ENV_FILE

    if not explicit.exists():
        print(f"Environment file not found: {explicit}", file=sys.stderr)
        raise SystemExit(2)

    env_map = dotenv_values(explicit)
    for key, value in env_map.items():
        if value is None:
            continue
        upper_key = key.upper()
        os.environ.setdefault(upper_key, value)
        os.environ.setdefault(key, value)

    os.environ.setdefault("SITE_MODE", "stg")
    os.environ.setdefault("SUPPRESS_DB_MESSAGES", "1")
    return explicit


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_date(dt: datetime) -> str:
    return _ensure_utc(dt).strftime("%B %d, %Y")


def _candidate_name(profile: Any) -> Optional[str]:
    user = getattr(profile, "user", None)
    if user is None:
        return None
    full_name = getattr(user, "full_name", None)
    if isinstance(full_name, str) and full_name.strip():
        return full_name.strip()
    first_raw = getattr(user, "first_name", "")
    last_raw = getattr(user, "last_name", "")
    first = first_raw.strip() if isinstance(first_raw, str) else ""
    last = last_raw.strip() if isinstance(last_raw, str) else ""
    combined = " ".join(part for part in (first, last) if part)
    return combined or None


def _expiry_recheck_url(frontend_url: str) -> str:
    return f"{frontend_url.rstrip('/')}/instructor/onboarding/verification"


def _build_email_payload(
    *,
    email_type: str,
    candidate: str,
    settings,
    profile: Any,
) -> tuple[str, TemplateRegistry, Dict[str, Any]]:
    from app.services.background_check_workflow_service import (
        EXPIRY_RECHECK_SUBJECT,
        FINAL_ADVERSE_SUBJECT,
        REVIEW_STATUS_SUBJECT,
    )
    from app.services.template_registry import TemplateRegistry

    now = datetime.now(timezone.utc)
    safe_name = candidate or ""

    if email_type == "pre":
        context: Dict[str, Any] = {
            "candidate_name": safe_name,
            "report_date": _format_date(now),
            "checkr_portal_url": settings.checkr_applicant_portal_url,
            "support_email": settings.bgc_support_email,
        }
        return REVIEW_STATUS_SUBJECT, TemplateRegistry.BGC_REVIEW_STATUS, context

    if email_type == "final":
        context = {
            "candidate_name": safe_name,
            "decision_date": _format_date(now),
            "checkr_portal_url": settings.checkr_applicant_portal_url,
            "checkr_dispute_url": settings.checkr_dispute_contact_url,
            "ftc_rights_url": settings.ftc_summary_of_rights_url,
            "support_email": settings.bgc_support_email,
        }
        return FINAL_ADVERSE_SUBJECT, TemplateRegistry.BGC_FINAL_ADVERSE, context

    expiry_dt = getattr(profile, "bgc_valid_until", None) if profile is not None else None
    if isinstance(expiry_dt, datetime):
        expiry_dt = _ensure_utc(expiry_dt)
    else:
        expiry_dt = now + timedelta(days=30)
    context = {
        "candidate_name": safe_name,
        "expiry_date": _format_date(expiry_dt),
        "is_past_due": expiry_dt < now,
        "recheck_url": _expiry_recheck_url(settings.frontend_url or "https://instainstru.com"),
        "support_email": settings.bgc_support_email,
    }
    return (
        EXPIRY_RECHECK_SUBJECT,
        TemplateRegistry.BGC_EXPIRY_RECHECK,
        context,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Send a background-check test email")
    parser.add_argument(
        "--type",
        required=True,
        choices=("pre", "final", "expiry"),
        help="Email type to send",
    )
    parser.add_argument("--email", required=True, help="Destination email address")
    parser.add_argument(
        "--instructor-id",
        default=None,
        help="Optional instructor profile ULID to personalise the email",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass suppression flags to send anyway",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to environment file (defaults to backend/.env)",
    )
    parser.add_argument(
        "--sender",
        choices=("trust", "bookings", "payments", "account"),
        default=None,
        help="Optional sender profile key to override template defaults",
    )

    args = parser.parse_args(argv)

    env_path = _ensure_env(args.env_file)

    try:
        from app.core.config import settings
        from app.core.exceptions import ServiceException
        from app.database import SessionLocal
        from app.repositories.instructor_profile_repository import InstructorProfileRepository
        from app.services.email import EmailService
        from app.services.sender_registry import get_sender
        from app.services.template_registry import get_default_sender_key
        from app.services.template_service import TemplateService
    except Exception as exc:  # noqa: BLE001 - runtime bootstrap guard
        print(f"Failed to import application modules: {exc}", file=sys.stderr)
        return 2

    if not settings.resend_api_key:
        print(
            "Resend API key is not configured. Provide one via the environment or --env-file.",
            file=sys.stderr,
        )
        return 2

    profile = None
    candidate = "Test Candidate"

    session = SessionLocal()
    try:
        if args.instructor_id:
            repo = InstructorProfileRepository(session)
            profile = repo.get_by_id(args.instructor_id, load_relationships=True)
            if profile is None:
                print(f"Instructor profile not found: {args.instructor_id}", file=sys.stderr)
                return 1
            candidate = _candidate_name(profile) or candidate

        subject, template, context = _build_email_payload(
            email_type=args.type,
            candidate=candidate,
            settings=settings,
            profile=profile,
        )

        print("Environment file :", env_path)
        print("Site mode        :", os.getenv("SITE_MODE", "<not set>"))
        print("Email type       :", args.type)
        print("Recipient        :", args.email)
        print("Subject          :", subject)
        print("Template         :", template.value)
        print("Context:")
        for key, value in context.items():
            print(f"  {key}: {value}")

        template_sender_key = get_default_sender_key(template)
        resolved_sender_key = args.sender or template_sender_key
        resolved_sender = get_sender(resolved_sender_key)

        print("Sender profile   :", resolved_sender_key or "<default>")
        print(
            f"From             : \"{resolved_sender['from_name']}\" <{resolved_sender['from_address']}>"
        )
        print(
            "Reply-To         :",
            resolved_sender["reply_to"] if resolved_sender["reply_to"] else "(none)",
        )

        suppressed = False
        if args.type in {"pre", "final"}:
            suppressed = bool(getattr(settings, "bgc_suppress_adverse_emails", True))
        else:
            suppressed = bool(getattr(settings, "bgc_suppress_expiry_emails", True))

        if suppressed and not args.force:
            print("\nSuppression is enabled. Email not sent (use --force to override).")
            return 0

        if suppressed and args.force:
            print("\nSuppression bypassed via --force; proceeding with send.")

        template_service = TemplateService(session)
        email_service = EmailService(session)

        merged_context = dict(context)
        merged_context.setdefault("subject", subject)

        html_content = template_service.render_template(template, context=merged_context)

        email_service.send_email(
            to_email=args.email,
            subject=subject,
            html_content=html_content,
            sender_key=resolved_sender_key,
            template=template,
        )

        print("\nEmail dispatched successfully.")
        return 0
    except ServiceException as exc:
        print(f"Failed to send email: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - final safety net for CLI usage
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
