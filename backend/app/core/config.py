# backend/app/core/config.py
from __future__ import annotations

from email.utils import parseaddr
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, NotRequired, Set, TypedDict, cast

if TYPE_CHECKING:
    load_dotenv: Callable[..., bool]
try:
    from dotenv import load_dotenv as _real_load_dotenv

    load_dotenv = cast(Callable[..., bool], _real_load_dotenv)
except Exception:  # pragma: no cover - optional on CI

    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


from pydantic import PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import BRAND_NAME
from .settings import (
    AuthSettingsMixin,
    AvailabilitySettingsMixin,
    CommunicationsSettingsMixin,
    DatabaseSettingsMixin,
    IntegrationsSettingsMixin,
    OperationsSettingsMixin,
    PaymentsSettingsMixin,
    PrivacySettingsMixin,
    RateLimitingSettingsMixin,
    ReferralsSettingsMixin,
    RuntimeSettingsMixin,
    SearchSettingsMixin,
)
from .settings.shared import (
    DEFAULT_SENDER_PROFILES_FILE,
    _classify_site_mode,
    _default_session_cookie_name,
    is_running_tests,
    resolve_referrals_step,
    secret_or_plain,
)

logger = logging.getLogger(__name__)

if not os.getenv("CI"):
    env_path = Path(__file__).parent.parent.parent / ".env"
    logger.info("[CONFIG] Looking for .env at: %s", env_path)
    logger.info("[CONFIG] .env exists: %s", env_path.exists())
    logger.info("[CONFIG] Absolute path: %s", env_path.absolute())
    load_dotenv(env_path)


class SenderProfile(TypedDict):
    from_name: str
    from_: str
    reply_to: NotRequired[str]


class SenderProfileResolved(TypedDict):
    from_name: str
    from_address: str
    reply_to: str | None


class Settings(
    ReferralsSettingsMixin,
    RateLimitingSettingsMixin,
    AvailabilitySettingsMixin,
    PrivacySettingsMixin,
    SearchSettingsMixin,
    OperationsSettingsMixin,
    PaymentsSettingsMixin,
    IntegrationsSettingsMixin,
    RuntimeSettingsMixin,
    CommunicationsSettingsMixin,
    DatabaseSettingsMixin,
    AuthSettingsMixin,
    BaseSettings,
):
    _sender_profiles: dict[str, SenderProfile] = PrivateAttr(default_factory=dict)
    _sender_profiles_warning_logged: bool = PrivateAttr(default=False)

    model_config = SettingsConfigDict(
        env_file=".env" if not os.getenv("CI") else None,
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def site_mode(self) -> str:
        """Return canonical site mode derived from SITE_MODE."""

        normalized, is_prod, _ = _classify_site_mode(os.getenv("SITE_MODE", ""))
        if normalized == "preview":
            return "preview"
        if is_prod:
            return "prod"
        return "local"

    @property
    def referrals_step(self) -> int:
        """Return resolved referrals issuance step honoring environment defaults."""

        return resolve_referrals_step(site_mode=self.site_mode)

    @property
    def metrics_basic_auth_enabled(self) -> bool:
        mode = (self.site_mode or "").lower()
        raw_mode = (os.getenv("SITE_MODE", "") or "").strip().lower()
        if mode not in {"preview", "prod"} and raw_mode != "beta":
            return False
        return self.metrics_basic_auth_user is not None and self.metrics_basic_auth_pass is not None

    def env_bool(self, name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @model_validator(mode="after")
    def _derive_cookie_policy(self) -> "Settings":
        """Normalize session cookie attributes per site mode."""

        raw_mode = (os.getenv("SITE_MODE", "") or "").strip().lower()
        normalized, is_prod, is_non_prod = _classify_site_mode(raw_mode or self.site_mode)
        hosted = normalized == "preview" or is_prod or normalized in {"stg", "stage", "staging"}

        if hosted:
            self.session_cookie_secure = True
            self.session_cookie_samesite = "lax"
            self.session_cookie_domain = ".instainstru.com"
        elif not is_prod and not is_non_prod:
            self.session_cookie_secure = bool(self.session_cookie_secure)

        if not bool(self.session_cookie_secure) and str(self.session_cookie_name or "").startswith(
            "__Host-"
        ):
            logger.warning(
                "SESSION_COOKIE_NAME %s uses __Host- prefix but SESSION_COOKIE_SECURE is false. "
                "Set SESSION_COOKIE_NAME=sid_local (or similar) or enable HTTPS.",
                self.session_cookie_name,
            )
        return self

    @model_validator(mode="after")
    def require_bgc_key_in_prod(self) -> "Settings":
        """Ensure encryption key is configured when running in production."""

        environment = (self.environment or "").strip().lower()
        if environment not in {"production", "development"}:
            environment = (
                "production" if _classify_site_mode(os.getenv("SITE_MODE"))[1] else "development"
            )
        key_value = secret_or_plain(self.bgc_encryption_key).strip()
        if environment == "production" and not key_value:
            raise ValueError("BGC_ENCRYPTION_KEY must be set in production environments.")
        return self

    @model_validator(mode="after")
    def require_stripe_secrets_in_prod(self) -> "Settings":
        """Ensure Stripe API and webhook secrets are configured when the app is
        actually serving HTTP traffic in production.

        The validator is opt-in via ``REQUIRE_STRIPE_SECRETS=1`` (or ``true``/``yes``),
        which the web server entrypoint sets. This keeps management scripts
        (``prep_db.py``), tests (``pytest``), CI import checks, and Alembic
        migrations from failing when they only need the DB — they don't touch
        Stripe and shouldn't force ops to set unrelated secrets.

        When ``REQUIRE_STRIPE_SECRETS`` is not set, the validator is silent.
        Without this guard the app would boot green with empty secrets and
        silently fail at the first webhook or PaymentIntent call, so the web
        server's start command MUST set it.
        """

        require_raw = os.getenv("REQUIRE_STRIPE_SECRETS", "").strip().lower()
        if require_raw not in {"1", "true", "yes", "on"}:
            return self

        if not secret_or_plain(self.stripe_secret_key).strip():
            raise ValueError("STRIPE_SECRET_KEY must be set in production environments.")
        if not secret_or_plain(self.stripe_webhook_secret_platform).strip():
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET_PLATFORM must be set in production environments."
            )
        if not secret_or_plain(self.stripe_webhook_secret_connect).strip():
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET_CONNECT must be set in production environments."
            )
        return self

    @model_validator(mode="after")
    def validate_test_database(self) -> "Settings":
        """Ensure test database is not a production database."""

        value_raw = secret_or_plain(self.int_database_url_raw).strip()
        if not value_raw:
            return self

        for indicator in [item.lower() for item in self.production_database_indicators]:
            if indicator and indicator in value_raw.lower():
                raise ValueError(
                    f"Test database URL contains production indicator '{indicator}'. "
                    f"Tests must not use production databases!"
                )

        test_indicators = ["test", "testing", "_test", "-test"]
        has_test_indicator = any(indicator in value_raw.lower() for indicator in test_indicators)
        if not has_test_indicator:
            logger.warning(
                "Test database URL doesn't contain 'test' in its name. "
                "Consider using a clearly named test database."
            )

        return self

    @model_validator(mode="after")
    def _load_sender_profiles(self) -> "Settings":
        self.refresh_sender_profiles(self.email_sender_profiles_json)
        return self

    @model_validator(mode="after")
    def _default_checkr_fake(self) -> "Settings":
        """Ensure FakeCheckr is enabled by default in non-production environments."""

        fields_set = cast(Set[str], getattr(self, "model_fields_set", set()))
        has_env_flag = "CHECKR_FAKE" in os.environ
        if "checkr_fake" not in fields_set and not has_env_flag:
            _, is_prod, is_non_prod = _classify_site_mode(os.getenv("SITE_MODE", ""))
            if is_non_prod and not is_prod:
                self.checkr_fake = True
            elif is_prod:
                self.checkr_fake = False
        return self

    def refresh_sender_profiles(self, raw_json: str | None = None) -> None:
        """Re-parse sender profiles from configuration file and JSON overlay."""

        if raw_json is not None:
            self.email_sender_profiles_json = raw_json

        file_profiles = self._load_sender_profiles_from_file(self.email_sender_profiles_file)
        env_profiles = self._parse_sender_profiles(
            self.email_sender_profiles_json,
            allow_partial=True,
        )

        merged: dict[str, SenderProfile] = {}
        for key in set(file_profiles) | set(env_profiles):
            base_profile = file_profiles.get(key)
            overrides = env_profiles.get(key, {})

            from_name = overrides.get("from_name")
            if not from_name and base_profile is not None:
                from_name = base_profile.get("from_name", "")

            from_address = overrides.get("from_")
            if not from_address and base_profile is not None:
                from_address = base_profile.get("from_", "")

            reply_override = overrides.get("reply_to")
            base_reply = base_profile.get("reply_to") if base_profile else None
            reply_to = reply_override if reply_override else base_reply

            if not from_name and not from_address and not reply_to:
                continue

            profile: SenderProfile = {
                "from_name": from_name or "",
                "from_": from_address or "",
            }
            if reply_to:
                profile["reply_to"] = reply_to
            merged[key] = profile

        self._sender_profiles = merged

    def resolve_sender_profile(self, key: str | None) -> SenderProfileResolved:
        """Return a resolved sender profile for the given key with defaults applied."""

        default_profile = self._default_sender_profile()
        if key:
            profile = self._sender_profiles.get(key)
            if profile:
                from_name = profile.get("from_name", "").strip() or default_profile["from_name"]
                from_address = profile.get("from_", "").strip() or default_profile["from_address"]
                reply_to_raw = profile.get("reply_to")
                reply_to = reply_to_raw.strip() if isinstance(reply_to_raw, str) else None
                if not reply_to:
                    reply_to = default_profile["reply_to"]
                return {
                    "from_name": from_name,
                    "from_address": from_address,
                    "reply_to": reply_to,
                }
        return default_profile

    def _load_sender_profiles_from_file(self, file_path: str | None) -> dict[str, SenderProfile]:
        if not file_path:
            return {}

        resolved_path = Path(file_path)
        if not resolved_path.is_absolute():
            try:
                repo_root = Path(__file__).resolve().parents[3]
            except IndexError:  # pragma: no cover - defensive fallback
                repo_root = Path.cwd()
            resolved_path = (repo_root / resolved_path).resolve()

        if not resolved_path.exists():
            self._log_sender_profile_warning(f"Sender profiles file not found: {resolved_path}")
            return {}

        try:
            raw = resolved_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem edge cases
            self._log_sender_profile_warning(
                f"Failed to read sender profiles file {resolved_path}: {exc}"
            )
            return {}

        parsed = self._parse_sender_profiles(raw, allow_partial=False)
        result: dict[str, SenderProfile] = {}
        for key, value in parsed.items():
            profile: SenderProfile = {
                "from_name": value.get("from_name", ""),
                "from_": value.get("from_", ""),
            }
            reply_to_value = value.get("reply_to")
            if reply_to_value:
                profile["reply_to"] = reply_to_value
            result[key] = profile
        return result

    def _parse_sender_profiles(
        self, raw: str | None, *, allow_partial: bool
    ) -> dict[str, dict[str, str]]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - log and ignore invalid env
            self._log_sender_profile_warning(f"Failed to parse EMAIL_SENDER_PROFILES_JSON: {exc}")
            return {}
        if not isinstance(data, dict):
            self._log_sender_profile_warning(
                "EMAIL_SENDER_PROFILES_JSON must decode to an object mapping"
            )
            return {}

        parsed: dict[str, dict[str, str]] = {}
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                logger.debug("Skipping invalid sender profile entry: %s", key)
                continue
            from_name = value.get("from_name")
            from_address = value.get("from") or value.get("from_")
            reply_to_value = value.get("reply_to")

            profile: dict[str, str] = {}
            if isinstance(from_name, str) and from_name.strip():
                profile["from_name"] = from_name.strip()
            elif isinstance(from_name, str) and allow_partial:
                profile["from_name"] = from_name.strip()

            if isinstance(from_address, str) and from_address.strip():
                profile["from_"] = from_address.strip()
            elif isinstance(from_address, str) and allow_partial:
                profile["from_"] = from_address.strip()

            if isinstance(reply_to_value, str):
                cleaned_reply = reply_to_value.strip()
                if cleaned_reply or allow_partial:
                    profile["reply_to"] = cleaned_reply

            if not allow_partial and ("from_name" not in profile or "from_" not in profile):
                logger.debug("Sender profile %s missing required fields", key)
                continue

            if profile:
                parsed[key] = profile
        return parsed

    def _default_sender_profile(self) -> SenderProfileResolved:
        name = (self.email_from_name or "").strip()
        address = (self.email_from_address or "").strip()

        parsed_name, parsed_address = parseaddr(self.from_email)
        if not name:
            name = parsed_name.strip() if parsed_name else BRAND_NAME
        if not address:
            address = parsed_address or "hello@instainstru.com"

        reply_to = (self.email_reply_to or "").strip()
        return {
            "from_name": name,
            "from_address": address,
            "reply_to": reply_to or None,
        }

    def _log_sender_profile_warning(self, message: str) -> None:
        if not self._sender_profiles_warning_logged:
            logger.warning(message)
            self._sender_profiles_warning_logged = True


def assert_env(
    site_mode_raw: str,
    checkr_env: str,
    *,
    fake: bool | None = None,
    allow_override: bool | None = None,
) -> None:
    """Apply Checkr environment guardrails based on SITE_MODE and toggles."""

    normalized_site_mode, is_prod, is_non_prod = _classify_site_mode(site_mode_raw)
    normalized_checkr_env = (checkr_env or "").strip().lower()

    if fake is None:
        effective_fake = settings.checkr_fake if not is_prod else False
    else:
        effective_fake = fake

    effective_override = (
        settings.allow_sandbox_checkr_in_prod if allow_override is None else allow_override
    )

    if is_prod:
        if normalized_checkr_env == "production":
            return
        if normalized_checkr_env == "sandbox" and (effective_fake or effective_override):
            logger.warning("Permitting CHECKR_ENV=sandbox in production due to FakeCheckr/override")
            return
        raise RuntimeError("Refusing to start: production requires CHECKR_ENV=production")

    if is_non_prod:
        if normalized_checkr_env == "sandbox":
            return
        raise RuntimeError("Refusing to start: non-prod requires CHECKR_ENV=sandbox")

    if normalized_checkr_env == "sandbox":
        return

    raise RuntimeError("Refusing to start: non-prod requires CHECKR_ENV=sandbox")


settings = Settings()
logger.info(
    "[CONFIG] Background check configuration: site_mode=%s checkr_env=%s checkr_fake=%s",
    settings.site_mode,
    settings.checkr_env,
    settings.checkr_fake,
)

__all__ = [
    "DEFAULT_SENDER_PROFILES_FILE",
    "SenderProfile",
    "SenderProfileResolved",
    "Settings",
    "_classify_site_mode",
    "_default_session_cookie_name",
    "assert_env",
    "is_running_tests",
    "resolve_referrals_step",
    "secret_or_plain",
    "settings",
]
