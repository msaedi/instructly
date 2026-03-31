from __future__ import annotations

from importlib import import_module
import logging
import os
from typing import TYPE_CHECKING, Any, Dict
from urllib.parse import ParseResult, urljoin, urlparse

from sqlalchemy.exc import IntegrityError
import stripe

from ...core.exceptions import ServiceException
from ...models.payment import StripeConnectedAccount
from ...models.user import User
from ...schemas.payment_schemas import (
    OnboardingResponse,
    OnboardingStatusResponse,
)
from ...utils.url_validation import (
    is_allowed_origin as _is_allowed_origin,
    origin_from_header as _origin_from_header,
)
from ..base import BaseService

if TYPE_CHECKING:
    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ...repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


class StripeOnboardingMixin(BaseService):
    """Instructor onboarding — Connect account creation, status, dashboard, payouts."""

    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository
    stripe_configured: bool
    if TYPE_CHECKING:

        def _call_with_retry(self, func: Any, *args: Any, **kwargs: Any) -> Any:
            ...

    def _require_instructor_profile(self, user: User) -> Any:
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")
        return profile

    def _require_connected_account_record(self, profile_id: str) -> Any:
        connected = self.payment_repository.get_connected_account_by_instructor_id(profile_id)
        if not connected or not connected.stripe_account_id:
            raise ServiceException("Instructor is not onboarded to Stripe", code="not_onboarded")
        return connected

    def _find_or_create_stripe_account(
        self, *, instructor_profile: Any, email: str
    ) -> tuple[str, bool]:
        existing_account = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if existing_account and existing_account.stripe_account_id:
            account_id = existing_account.stripe_account_id
            account_status = self.check_account_status(instructor_profile.id)
            if account_status.get("onboarding_completed"):
                return account_id, True
            return account_id, False

        return self.create_connected_account(instructor_profile.id, email).stripe_account_id, False

    def _extract_callback_from_return_to(self, return_to: str | None) -> str | None:
        callback_from: str | None = None
        if return_to and return_to.startswith("/"):
            parsed_return = urlparse(return_to)
            redirect_path = (parsed_return.path or "").strip().lower()
            if redirect_path:
                segments = [segment for segment in redirect_path.split("/") if segment]
                if (
                    len(segments) >= 3
                    and segments[0] == "instructor"
                    and segments[1] == "onboarding"
                ):
                    callback_from = segments[2]
                elif len(segments) >= 2 and segments[0] == "instructor":
                    callback_from = segments[1]
                elif segments:
                    callback_from = segments[-1]

        if not callback_from:
            return None

        sanitized = "".join(ch for ch in callback_from if ch.isalnum() or ch in {"-", "_"})
        return sanitized or None

    def _normalize_origin(self, raw: str | None, *, request_scheme: str) -> str | None:
        if not raw:
            return None
        parsed_raw: ParseResult = urlparse(raw)
        scheme = parsed_raw.scheme or request_scheme
        if parsed_raw.netloc:
            return f"{scheme}://{parsed_raw.netloc}".rstrip("/")
        if parsed_raw.path and raw.startswith(("http://", "https://")):
            return raw.rstrip("/")
        return None

    def _resolve_onboarding_origin(
        self,
        *,
        request_host: str,
        request_scheme: str,
        request_origin: str | None,
        request_referer: str | None,
    ) -> str:
        settings = _stripe_service_module().settings
        facade_module = _stripe_service_module()
        origin_from_header = getattr(facade_module, "origin_from_header", _origin_from_header)
        is_allowed_origin = getattr(facade_module, "is_allowed_origin", _is_allowed_origin)
        configured_frontend = (settings.frontend_url or "").strip()
        local_frontend = (settings.local_beta_frontend_origin or "").strip()
        request_host_clean = (request_host or "").strip()
        origin_candidates: list[str] = []
        header_origin = origin_from_header(request_origin) or origin_from_header(request_referer)
        if header_origin and is_allowed_origin(header_origin):
            origin_candidates.append(header_origin)
        if configured_frontend:
            origin_candidates.append(configured_frontend)
        request_host_lower = request_host_clean.lower()
        parsed_front = urlparse(configured_frontend) if configured_frontend else None
        configured_hostname = (parsed_front.hostname or "").lower() if parsed_front else ""
        if (
            request_host_lower.startswith("api.")
            and configured_hostname
            and request_host_lower.split(":", 1)[0].removeprefix("api.") == configured_hostname
        ):
            scheme = parsed_front.scheme or request_scheme if parsed_front else request_scheme
            origin_candidates.append(f"{scheme}://{configured_hostname}".rstrip("/"))
        if local_frontend:
            origin_candidates.append(local_frontend)
        for candidate in origin_candidates:
            origin = self._normalize_origin(candidate, request_scheme=request_scheme)
            if origin:
                return origin
        origin = self._normalize_origin(configured_frontend, request_scheme=request_scheme)
        if origin:
            return origin
        return f"{request_scheme}://{request_host_clean}".rstrip("/")

    def _build_onboarding_paths(self, callback_from: str | None) -> tuple[str, str]:
        if callback_from == "payment-setup":
            success_path = "/instructor/onboarding/payment-setup"
        else:
            success_path = (
                f"/instructor/onboarding/status/{callback_from}"
                if callback_from
                else "/instructor/onboarding/status"
            )
        return "/instructor/onboarding/start", success_path

    @BaseService.measure_operation("stripe_start_instructor_onboarding")
    def start_instructor_onboarding(
        self,
        *,
        user: User,
        request_host: str,
        request_scheme: str,
        request_origin: str | None = None,
        request_referer: str | None = None,
        return_to: str | None = None,
    ) -> OnboardingResponse:
        instructor_profile = self.instructor_repository.get_by_user_id(user.id)
        if not instructor_profile:
            raise ServiceException(
                "Instructor profile not found",
                code="PAYMENTS_INSTRUCTOR_PROFILE_NOT_FOUND",
            )

        account_id, already_onboarded = self._find_or_create_stripe_account(
            instructor_profile=instructor_profile,
            email=user.email,
        )
        if already_onboarded:
            return OnboardingResponse(
                account_id=account_id, onboarding_url="", already_onboarded=True
            )

        callback_from = self._extract_callback_from_return_to(return_to)
        origin = self._resolve_onboarding_origin(
            request_host=request_host,
            request_scheme=request_scheme,
            request_origin=request_origin,
            request_referer=request_referer,
        )
        refresh_path, success_path = self._build_onboarding_paths(callback_from)
        onboarding_link = self.create_account_link(
            instructor_profile_id=instructor_profile.id,
            refresh_url=urljoin(origin + "/", refresh_path.lstrip("/")),
            return_url=urljoin(origin + "/", success_path.lstrip("/")),
        )
        return OnboardingResponse(
            account_id=account_id, onboarding_url=onboarding_link, already_onboarded=False
        )

    @BaseService.measure_operation("stripe_get_onboarding_status")
    def get_instructor_onboarding_status(self, *, user: User) -> OnboardingStatusResponse:
        profile = self._require_instructor_profile(user)
        connected = self.payment_repository.get_connected_account_by_instructor_id(profile.id)
        if not connected or not connected.stripe_account_id:
            return OnboardingStatusResponse(
                has_account=False,
                onboarding_completed=False,
                charges_enabled=False,
                payouts_enabled=False,
                details_submitted=False,
                requirements=[],
            )

        account = self.check_account_status(profile.id)
        charges_enabled = bool(
            account.get("charges_enabled", account.get("can_accept_payments", False))
        )
        payouts_enabled = bool(account.get("payouts_enabled", False))
        details_submitted = bool(account.get("details_submitted", False))
        onboarding_completed = bool(account.get("onboarding_completed", False))
        requirements_list: list[str] = account.get("requirements", []) or []
        return OnboardingStatusResponse(
            has_account=True,
            onboarding_completed=onboarding_completed,
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            details_submitted=details_submitted,
            requirements=requirements_list,
        )

    def _persist_connected_account_record(
        self, *, instructor_profile_id: str, stripe_account_id: str
    ) -> StripeConnectedAccount:
        try:
            with self.payment_repository.transaction():
                return self.payment_repository.create_connected_account_record(
                    instructor_profile_id=instructor_profile_id,
                    stripe_account_id=stripe_account_id,
                    onboarding_completed=False,
                )
        except IntegrityError:
            existing_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if existing_record:
                return existing_record
            raise

    def _build_connect_account_params(
        self, *, instructor_profile_id: str, email: str
    ) -> dict[str, Any]:
        return {
            "type": "express",
            "email": email,
            "capabilities": {"transfers": {"requested": True}},
            "metadata": {"instructor_profile_id": instructor_profile_id},
            "idempotency_key": f"acct_{instructor_profile_id}",
        }

    def _create_stripe_connect_account(self, *, instructor_profile_id: str, email: str) -> Any:
        stripe_sdk = _stripe_service_module().stripe
        return self._call_with_retry(
            stripe_sdk.Account.create,
            **self._build_connect_account_params(
                instructor_profile_id=instructor_profile_id, email=email
            ),
        )

    def _apply_default_payout_schedule(self, stripe_account_id: str) -> None:
        stripe_sdk = _stripe_service_module().stripe
        try:
            stripe_sdk.Account.modify(
                stripe_account_id,
                settings={
                    "payouts": {"schedule": {"interval": "weekly", "weekly_anchor": "tuesday"}}
                },
            )
        except Exception:
            logger.warning("Non-fatal error ignored", exc_info=True)

    def _create_mock_connected_account(
        self, *, instructor_profile_id: str, error: Exception
    ) -> StripeConnectedAccount:
        if os.getenv("INSTAINSTRU_PRODUCTION_MODE", "").lower() == "true":
            raise ServiceException(
                "Stripe not configured in production mode", code="configuration_error"
            )
        self.logger.warning(
            "Stripe not configured or call failed (%s); using mock connected account for instructor %s",
            str(error),
            instructor_profile_id,
        )
        try:
            return self._persist_connected_account_record(
                instructor_profile_id=instructor_profile_id,
                stripe_account_id=f"mock_acct_{instructor_profile_id}",
            )
        except IntegrityError as conflict:
            self.logger.warning(
                "Race detected creating mock account for instructor %s: %s",
                instructor_profile_id,
                str(conflict),
            )
            existing_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if existing_record:
                return existing_record
            raise ServiceException(
                "Failed to create connected account due to conflict"
            ) from conflict

    @BaseService.measure_operation("stripe_create_connected_account")
    def create_connected_account(
        self, instructor_profile_id: str, email: str
    ) -> StripeConnectedAccount:
        existing = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile_id
        )
        if existing:
            return existing
        try:
            stripe_account = self._create_stripe_connect_account(
                instructor_profile_id=instructor_profile_id,
                email=email,
            )
            account_record = self._persist_connected_account_record(
                instructor_profile_id=instructor_profile_id,
                stripe_account_id=stripe_account.id,
            )
            self._apply_default_payout_schedule(stripe_account.id)
            self.logger.info(
                "Created Stripe Express account %s...%s for instructor %s",
                stripe_account.id[:8],
                stripe_account.id[-4:],
                instructor_profile_id,
            )
            return account_record
        except IntegrityError as exc:
            self.logger.warning(
                "Race detected creating connected account for instructor %s: %s",
                instructor_profile_id,
                str(exc),
            )
            existing_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if existing_record:
                return existing_record
            raise ServiceException("Failed to create connected account due to conflict") from exc
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating connected account: %s", exc)
            raise ServiceException(f"Failed to create connected account: {exc}")
        except Exception as exc:
            if not self.stripe_configured:
                return self._create_mock_connected_account(
                    instructor_profile_id=instructor_profile_id,
                    error=exc,
                )
            self.logger.error("Error creating connected account: %s", exc)
            raise ServiceException(f"Failed to create connected account: {str(exc)}")

    @BaseService.measure_operation("stripe_create_account_link")
    def create_account_link(
        self, instructor_profile_id: str, refresh_url: str, return_url: str
    ) -> str:
        facade_module = _stripe_service_module()
        stripe_sdk = facade_module.stripe
        try:
            account_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account_record:
                raise ServiceException(
                    f"No connected account found for instructor {instructor_profile_id}"
                )
            account_link = stripe_sdk.AccountLink.create(
                account=account_record.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_onboarding",
                idempotency_key=f"acct_link_{instructor_profile_id}_{facade_module.uuid.uuid4()}",
            )
            self.logger.info("Created account link for instructor %s", instructor_profile_id)
            url_attr = getattr(account_link, "url", None)
            return str(url_attr) if url_attr is not None else ""
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating account link: %s", exc)
            raise ServiceException(f"Failed to create account link: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error creating account link: %s", exc)
            raise ServiceException(f"Failed to create account link: {str(exc)}")

    @BaseService.measure_operation("stripe_check_account_status")
    def check_account_status(self, instructor_profile_id: str) -> Dict[str, Any]:
        stripe_sdk = _stripe_service_module().stripe
        try:
            account_record = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile_id
            )
            if not account_record:
                return {
                    "has_account": False,
                    "onboarding_completed": False,
                    "charges_enabled": False,
                    "can_accept_payments": False,
                    "payouts_enabled": False,
                    "details_submitted": False,
                    "requirements": [],
                }

            stripe_account = stripe_sdk.Account.retrieve(account_record.stripe_account_id)
            charges_enabled = bool(getattr(stripe_account, "charges_enabled", False))
            payouts_enabled = bool(getattr(stripe_account, "payouts_enabled", False))
            details_submitted = bool(getattr(stripe_account, "details_submitted", False))
            requirements: list[str] = []
            try:
                requirements_obj = getattr(stripe_account, "requirements", None)
                if requirements_obj:
                    for field_name in ("currently_due", "past_due", "pending_verification"):
                        items = getattr(requirements_obj, field_name, None) or []
                        if isinstance(items, (list, tuple, set)):
                            for item in items:
                                if isinstance(item, str):
                                    requirements.append(item)
            except Exception as exc:
                logger.warning(
                    "Failed to inspect Stripe account requirements for %s: %s",
                    account_record.stripe_account_id,
                    str(exc),
                    exc_info=True,
                )
                requirements = []

            computed_completed = bool(charges_enabled and details_submitted)
            if account_record.onboarding_completed != computed_completed:
                try:
                    self.payment_repository.update_onboarding_status(
                        account_record.stripe_account_id,
                        computed_completed,
                    )
                    account_record.onboarding_completed = computed_completed
                except Exception as exc:
                    logger.warning(
                        "Failed to persist onboarding status for %s: %s",
                        account_record.stripe_account_id,
                        str(exc),
                        exc_info=True,
                    )
            return {
                "has_account": True,
                "onboarding_completed": computed_completed,
                "charges_enabled": charges_enabled,
                "can_accept_payments": charges_enabled,
                "payouts_enabled": payouts_enabled,
                "details_submitted": details_submitted,
                "requirements": requirements,
                "stripe_account_id": account_record.stripe_account_id,
            }
        except stripe.StripeError as exc:
            self.logger.error("Stripe error checking account status: %s", exc)
            raise ServiceException(f"Failed to check account status: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error checking account status: %s", exc)
            raise ServiceException(f"Failed to check account status: {str(exc)}")
