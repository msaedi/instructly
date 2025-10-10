"""Simulate Checkr background check flows by instructor email.

Defaults to STG by reading `backend/.env` and selecting `stg_database_url`. No
`.env.stg` is required. Use `--env` to pick beta/int/prod, or `--env-file` to point
at a custom env file.

Usage examples:
  # simplest: defaults to staging using backend/.env
  python backend/scripts/simulate_checkr_webhook.py --email 'owner@example.com' --result clear

  # beta
  python backend/scripts/simulate_checkr_webhook.py --env beta --email 'owner@example.com' --result consider

  # reset (re-enable Start button)
  python backend/scripts/simulate_checkr_webhook.py --email 'owner@example.com' --reset

Safety:
  - Refuses to run in production unless --force-prod is provided.
"""

# ruff: noqa: I001

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values
from sqlalchemy import func


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_CHOICES: Sequence[str] = ("local", "int", "stg", "preview", "beta", "prod")
DEFAULT_ENV = "stg"
WEBHOOK_PATH = "/webhooks/checkr/"
REQUEST_HOST_FALLBACK = "localhost:8000"


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bootstrap_env(env: Optional[str], env_file: Optional[str]) -> str:
    env_name = (env or DEFAULT_ENV).lower()

    if env_file:
        explicit = Path(env_file).expanduser().resolve()
        if not explicit.exists():
            print(f"Provided --env-file does not exist: {explicit}", file=sys.stderr)
            sys.exit(2)
        env_map = dotenv_values(explicit)
        loaded_from = str(explicit)
    else:
        backend_env = Path(__file__).resolve().parents[2] / "backend" / ".env"
        if not backend_env.exists():
            print("backend/.env not found; provide --env-file", file=sys.stderr)
            sys.exit(2)
        env_map = dotenv_values(backend_env)
        loaded_from = str(backend_env)

    key_map = {
        "int": "test_database_url",
        "stg": "stg_database_url",
        "preview": "preview_database_url",
        "beta": "prod_database_url",
        "prod": "prod_database_url",
    }
    service_key_map = {
        "preview": "preview_service_database_url",
        "beta": "prod_service_database_url",
        "prod": "prod_service_database_url",
    }

    db_key = key_map.get(env_name, "stg_database_url")
    db_url = (env_map.get(db_key) or "").strip()
    if not db_url:
        print(f"Missing {db_key} in {loaded_from}", file=sys.stderr)
        sys.exit(2)

    if env_name != "int" and "instainstru_test" in db_url:
        print("Refusing to use test database outside --env int", file=sys.stderr)
        sys.exit(2)

    service_key = service_key_map.get(env_name)
    service_url = (env_map.get(service_key) or "").strip() if service_key else ""
    if service_url:
        db_url = service_url

    os.environ["DATABASE_URL"] = db_url
    if env_name == "stg" and "SITE_MODE" not in os.environ:
        os.environ["SITE_MODE"] = "stg"
    elif env_name == "int" and "SITE_MODE" not in os.environ:
        os.environ["SITE_MODE"] = "int"
    elif env_name in {"beta", "prod"}:
        os.environ["SITE_MODE"] = "prod"
    elif env_name == "preview":
        os.environ["SITE_MODE"] = "preview"
    elif env_name == "local" and "SITE_MODE" not in os.environ:
        os.environ["SITE_MODE"] = "local"

    os.environ.setdefault("CHECKR_ENV", "sandbox")
    os.environ.setdefault("CHECKR_FAKE", "true")

    secret_from_env = None
    for key in ("CHECKR_WEBHOOK_SECRET", "checkr_webhook_secret"):
        value = env_map.get(key)
        if value:
            secret_from_env = value.strip()
            break
    if secret_from_env:
        os.environ["CHECKR_WEBHOOK_SECRET"] = secret_from_env
    os.environ.setdefault("CHECKR_WEBHOOK_SECRET", "whsec_test")
    if env_name in {"local", "stg", "int"}:
        os.environ.setdefault("CHECKR_WEBHOOK_URL", "http://localhost:8000/webhooks/checkr/")
    else:
        if os.environ.get("CHECKR_WEBHOOK_URL", "").startswith("http://localhost"):
            os.environ.pop("CHECKR_WEBHOOK_URL", None)
    os.environ.setdefault("SUPPRESS_DB_MESSAGES", "1")
    os.environ["SIM_ENV_FILE"] = loaded_from
    os.environ["SIM_ENV_NAME"] = env_name

    if "@anon" in db_url or ":anon@" in db_url:
        print(
            "⚠️  WARNING: Using anon-level database credentials; queries may be restricted.",
            file=sys.stderr,
        )
    return env_name


def _redact_database_url(raw_url: str | None) -> str:
    if not raw_url:
        return "<unknown>"

    parsed = urlparse(raw_url)
    scheme = parsed.scheme or ""

    if scheme.startswith("sqlite"):
        path = parsed.path or parsed.netloc or ""
        return f"{scheme}://{path.lstrip('/')}"

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db_name = parsed.path.lstrip("/") if parsed.path else ""
    parts = []
    if host:
        parts.append(host)
    if port:
        parts.append(port)
    if db_name:
        parts.append(f"/{db_name}")
    masked_host = "".join(parts) if parts else raw_url
    return masked_host


def _resolve_origin_from_host(host: str, *, site_mode: str) -> str:
    trimmed = host.strip()
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed.rstrip("/")
    scheme = "https" if site_mode == "prod" else "http"
    return f"{scheme}://{trimmed.lstrip('/')}"


def _resolve_webhook_url(
    *,
    explicit: Optional[str],
    current_settings,
    environment: str,
) -> str:
    if explicit:
        return explicit

    env_override = os.getenv("CHECKR_WEBHOOK_URL")
    if env_override:
        return env_override

    canonical = environment.strip().lower()
    if canonical in {"beta", "prod"}:
        return "https://api.instainstru.com/webhooks/checkr/"
    if canonical == "preview":
        return "https://preview-api.instainstru.com/webhooks/checkr/"
    return "http://localhost:8000/webhooks/checkr/"


def _secret_value(secret: object | None) -> str:
    if secret is None:
        return ""
    getter = getattr(secret, "get_secret_value", None)
    if callable(getter):
        return str(getter())
    return str(secret)


def _post_webhook_via_asgi(target_url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    from urllib.parse import urlparse

    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme or 'http'}://{parsed.netloc or 'webhook.local'}"
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    from app.main import app as fastapi_app

    async def _send() -> tuple[int, str]:
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            response = await client.post(path, content=body, headers=headers)
            return response.status_code, response.text

    return asyncio.run(_send())


def _dispatch_webhook(webhook_url: str, raw_body: bytes, signature: str) -> tuple[int, str]:
    request = urllib.request.Request(
        webhook_url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Checkr-Signature": signature,
        },
    )

    def _invoke_internal() -> tuple[int, str]:
        return _post_webhook_via_asgi(
            webhook_url,
            raw_body,
            {
                "Content-Type": "application/json",
                "X-Checkr-Signature": signature,
            },
        )

    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            response_body = response.read().decode("utf-8")
            return response.status, response_body
    except urllib.error.HTTPError as exc:  # pragma: no cover
        if exc.code >= 500:
            status_code, response_body = _invoke_internal()
            return status_code, response_body
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"Webhook failed -> {exc.code}: {detail}")
    except urllib.error.URLError:
        status_code, response_body = _invoke_internal()
        return status_code, response_body


def _get_bgc_client(current_settings):
    from app.integrations.checkr_client import CheckrClient, FakeCheckrClient

    site_mode = getattr(current_settings, "site_mode", "local")
    if site_mode != "prod" or _truthy(os.getenv("CHECKR_FAKE")):
        return FakeCheckrClient()

    return CheckrClient(
        api_key=current_settings.checkr_api_key,
        base_url=current_settings.checkr_api_base,
    )


async def _ensure_invite(service, profile) -> Optional[str]:
    result = await service.invite(profile.id)
    return result.get("report_id")


def main() -> None:
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        choices=ENV_CHOICES,
        default=DEFAULT_ENV,
        help="Environment shortcut (default: stg)",
    )
    env_parser.add_argument("--env-file", dest="env_file", help="Explicit .env file to load", default=None)
    env_parser.add_argument(
        "--force-prod",
        dest="force_prod",
        action="store_true",
        help="Allow execution when SITE_MODE resolves to production",
    )

    pre_args, remaining_args = env_parser.parse_known_args()
    environment_name = _bootstrap_env(pre_args.environment, pre_args.env_file)

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from app.core.config import settings
    from app.database import SessionLocal
    from app.models.instructor import InstructorProfile
    from app.models.user import User
    from app.repositories.instructor_profile_repository import InstructorProfileRepository
    from app.services.background_check_service import BackgroundCheckService

    resolved_db_url = (os.getenv("DATABASE_URL") or "").lower()
    resolved_site_mode = (os.getenv("SITE_MODE") or getattr(settings, "site_mode", "") or "").lower()
    if environment_name != "int" and (
        "instainstru_test" in resolved_db_url or resolved_site_mode == "int"
    ):
        print(
            "Aborting: resolved to INT (test) database unexpectedly. "
            "Pass --env-file explicitly or ensure backend/.env has stg_database_url set.",
            file=sys.stderr,
        )
        sys.exit(2)

    parser = argparse.ArgumentParser(
        description="Simulate a Checkr webhook by instructor email",
        parents=[env_parser],
    )
    parser.add_argument("--email", required=True, help="Instructor email address")
    parser.add_argument(
        "--result",
        choices=["clear", "consider"],
        default="clear",
        help="Report result to simulate (default: clear)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Override webhook URL (otherwise derived from settings)",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="Override webhook signing secret",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the instructor's background check status to failed (non-prod only)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt when targeting live environments",
    )
    parser.add_argument(
        "--debug-sign",
        action="store_true",
        help="Print request body/signature diagnostics",
    )
    parser.add_argument(
        "--sig-format",
        choices=["raw", "sha256"],
        default="raw",
        help="Format for X-Checkr-Signature header (default: raw)",
    )

    args = parser.parse_args(remaining_args, namespace=pre_args)

    site_mode = getattr(settings, "site_mode", getattr(settings, "environment", "local"))
    if str(site_mode).lower() in {"prod", "production"} and not args.force_prod:
        print("Refusing to run: resolved SITE_MODE=production (use --force-prod to override).", file=sys.stderr)
        sys.exit(2)

    webhook_url = _resolve_webhook_url(
        explicit=args.url,
        current_settings=settings,
        environment=environment_name,
    )

    display_db = _redact_database_url(os.getenv("DATABASE_URL"))
    env_file = os.getenv("SIM_ENV_FILE", "backend/.env")
    print(
        f"Using ENV={environment_name} DB={display_db} WEBHOOK_URL={webhook_url} ENV_FILE={env_file}"
    )

    is_live_target = environment_name in {"beta", "prod"} and webhook_url.startswith("https://")
    if is_live_target and not args.yes:
        try:
            confirmation = input(
                "This will POST a simulated Checkr webhook to LIVE. Type 'yes' to continue: "
            )
        except KeyboardInterrupt:
            print("\nAborted by user.")
            sys.exit(1)
        if confirmation.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    db = SessionLocal()
    try:
        normalized_email = args.email.strip().lower()

        user: Optional[User] = (
            db.query(User)
            .filter(func.lower(User.email) == normalized_email)
            .one_or_none()
        )
        if not user:
            print(f"User not found for email: {args.email}", file=sys.stderr)
            sys.exit(1)

        profile: Optional[InstructorProfile] = (
            db.query(InstructorProfile).filter(InstructorProfile.user_id == user.id).one_or_none()
        )
        if not profile:
            if str(site_mode).lower() in {"prod", "production"}:
                print(
                    f"Instructor profile not found for user: {args.email}",
                    file=sys.stderr,
                )
                sys.exit(1)

            profile = InstructorProfile(
                user_id=user.id,
                bgc_status="failed",
                bgc_env=settings.checkr_env,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)

        if args.reset:
            profile.bgc_status = "failed"
            profile.bgc_report_id = None
            profile.bgc_completed_at = None
            db.commit()
            print(f"Reset complete for {args.email}")
            return

        repository = InstructorProfileRepository(db)
        client = _get_bgc_client(settings)
        service = BackgroundCheckService(
            db,
            client=client,
            repository=repository,
            package=settings.checkr_package,
            env=settings.checkr_env,
        )

        report_id = profile.bgc_report_id
        needs_invite = not report_id or (profile.bgc_status or "").lower() == "failed"

        if needs_invite:
            report_id = asyncio.run(_ensure_invite(service, profile))
            db.refresh(profile)
            report_id = report_id or profile.bgc_report_id

        if not report_id:
            print("Unable to determine background check report_id for webhook simulation.", file=sys.stderr)
            sys.exit(1)

        payload = {
            "type": "report.completed",
            "data": {
                "object": {
                    "id": report_id,
                    "status": "completed",
                "result": args.result,
            }
        },
        }

        raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        secret_value = (
            args.secret
            or os.getenv("CHECKR_WEBHOOK_SECRET")
            or _secret_value(getattr(settings, "checkr_webhook_secret", None))
            or "whsec_test"
        )
        secret_bytes = str(secret_value).encode("utf-8")
        signature = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()
        header_signature = signature if args.sig_format == "raw" else f"sha256={signature}"

        if args.debug_sign:
            preview_prefix = raw_body[:80]
            preview_suffix = raw_body[-80:] if len(raw_body) > 80 else b""
            warning = ""
            if secret_value.strip() != secret_value:
                warning = " (warning: secret has leading/trailing whitespace)"
            elif '"' in secret_value:
                warning = " (warning: secret contains quote characters)"
            print(
                "-- Debug Sign --",
                f"length={len(raw_body)}",
                f"head={preview_prefix!r}",
                f"tail={preview_suffix!r}",
                f"secret_len={len(secret_value)}",
                f"signature={signature}",
                f"header_signature={header_signature}",
                f"lowercase_hex={signature == signature.lower()}" + warning,
                sep="\n",
            )

        status_code, response_body = _dispatch_webhook(
            webhook_url, raw_body, header_signature
        )
        if 200 <= status_code < 300:
            print(f"Webhook dispatched -> {status_code}: {response_body}")
        else:
            print(f"Webhook failed -> {status_code}: {response_body}", file=sys.stderr)
            sys.exit(1)

        # Refresh profile to reflect webhook update; fallback to direct service update if needed
        db.expire_all()
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == user.id)
            .one()
        )
        if (
            args.result == "clear"
            and (profile.bgc_status or "").lower() != "passed"
        ):
            service.update_status_from_report(report_id, status="passed", completed=True)
            db.expire_all()
            profile = (
                db.query(InstructorProfile)
                .filter(InstructorProfile.user_id == user.id)
                .one()
            )
            if (profile.bgc_status or "").lower() != "passed":
                print(
                    "Unable to mark background check as passed after webhook.",
                    file=sys.stderr,
                )
                sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
