from __future__ import annotations

from datetime import date, datetime, timezone
from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

import stripe

from ...core.exceptions import ServiceException
from ...models.user import User
from ...schemas.payment_schemas import IdentityRefreshResponse
from ...utils.identity import clean_identity_value, normalize_name, redact_name
from ..base import BaseService

if TYPE_CHECKING:
    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ...repositories.user_repository import UserRepository
    from ..stripe_service import StripeServiceModuleProtocol

logger = logging.getLogger(__name__)


def _stripe_service_module() -> StripeServiceModuleProtocol:
    return cast("StripeServiceModuleProtocol", import_module("app.services.stripe_service"))


class StripeIdentityMixin(BaseService):
    """Stripe Identity verification — sessions, status, parsing, and persistence."""

    instructor_repository: InstructorProfileRepository
    user_repository: UserRepository

    if TYPE_CHECKING:

        def _check_stripe_configured(self) -> None:
            ...

        def _stripe_has_field(self, obj: Any, key: str) -> bool:
            ...

        def _stripe_value(self, obj: Any, key: str, default: Any = None) -> Any:
            ...

    def _identity_last_error(self, session: Any) -> tuple[Optional[str], Optional[str]]:
        """Extract last_error code/reason from a Stripe Identity session."""
        last_error = self._stripe_value(session, "last_error")
        if not last_error:
            return None, None
        code = self._stripe_value(last_error, "code")
        reason = self._stripe_value(last_error, "reason")
        return code, reason

    @staticmethod
    def _identity_retrieve_options() -> Dict[str, Any]:
        """Return Stripe Identity session retrieve options, including sensitive expansions."""
        settings = _stripe_service_module().settings
        api_key = None
        if settings.stripe_identity_restricted_key:
            api_key = settings.stripe_identity_restricted_key.get_secret_value()
        return {
            "expand": ["verified_outputs", "verified_outputs.dob"],
            "api_key": api_key,
        }

    def _parse_identity_dob(self, dob_value: Any) -> Optional[date]:
        """Convert Stripe DOB payloads into a Python date."""
        if not dob_value:
            return None

        day = self._stripe_value(dob_value, "day")
        month = self._stripe_value(dob_value, "month")
        year = self._stripe_value(dob_value, "year")
        if day in (None, "") or month in (None, "") or year in (None, ""):
            return None

        try:
            return date(int(year), int(month), int(day))
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid DOB components from Stripe: %s", exc)
            return None

    def _persist_verified_identity(
        self,
        *,
        profile_id: str,
        user_id: str,
        session: Any,
        session_id: str | None = None,
        refresh_session: bool = False,
        prefetched_session: Any | None = None,
    ) -> None:
        """Persist verified Stripe Identity outputs and mismatch flags on the instructor."""
        stripe_sdk = _stripe_service_module().stripe
        resolved_session = prefetched_session if prefetched_session is not None else session
        resolved_session_id = clean_identity_value(
            self._stripe_value(resolved_session, "id", session_id) or session_id
        )
        verified_at = datetime.now(timezone.utc)

        if refresh_session and prefetched_session is None and resolved_session_id:
            try:
                resolved_session = cast(Any, stripe_sdk.identity.VerificationSession).retrieve(
                    resolved_session_id,
                    **self._identity_retrieve_options(),
                )
            except stripe.StripeError as exc:
                self.logger.warning(
                    "Failed to retrieve Stripe verified outputs for session %s: %s",
                    resolved_session_id,
                    str(exc),
                )
                self.instructor_repository.update(
                    profile_id,
                    identity_verified_at=verified_at,
                    identity_verification_session_id=resolved_session_id,
                )
                return

        verified_outputs = (
            self._stripe_value(resolved_session, "verified_outputs")
            if self._stripe_has_field(resolved_session, "verified_outputs")
            else None
        )
        verified_first_name = clean_identity_value(
            self._stripe_value(verified_outputs, "first_name") if verified_outputs else None
        )
        verified_last_name = clean_identity_value(
            self._stripe_value(verified_outputs, "last_name") if verified_outputs else None
        )
        verified_dob = self._parse_identity_dob(
            self._stripe_value(verified_outputs, "dob") if verified_outputs else None
        )

        identity_name_mismatch = False
        user = self.user_repository.get_by_id(user_id)
        if user and verified_last_name:
            signup_last_name = normalize_name(getattr(user, "last_name", None))
            verified_last_name_normalized = normalize_name(verified_last_name)
            identity_name_mismatch = bool(
                signup_last_name
                and verified_last_name_normalized
                and signup_last_name != verified_last_name_normalized
            )
            if identity_name_mismatch:
                self.logger.warning(
                    "Identity last-name mismatch for user %s: signup_last=%s verified_last=%s",
                    user_id,
                    redact_name(getattr(user, "last_name", None)),
                    redact_name(verified_last_name),
                )

        self.instructor_repository.update(
            profile_id,
            identity_verified_at=verified_at,
            identity_verification_session_id=resolved_session_id,
            verified_first_name=verified_first_name,
            verified_last_name=verified_last_name,
            verified_dob=verified_dob,
            identity_name_mismatch=identity_name_mismatch,
        )

        if verified_outputs is None:
            self.logger.warning(
                "Stripe identity session %s verified without verified_outputs payload",
                resolved_session_id or "unknown",
            )

    def _identity_session_payload(self, session: Any, *, reuse_existing: bool) -> Dict[str, str]:
        """Return the API payload for a Stripe Identity session."""
        client_secret = self._stripe_value(session, "client_secret")
        if not client_secret:
            if reuse_existing:
                raise ServiceException("Failed to resume identity verification")
            raise ServiceException("Failed to create identity verification session")

        session_id = self._stripe_value(session, "id")
        if not session_id:
            if reuse_existing:
                raise ServiceException("Failed to resume identity verification")
            raise ServiceException("Failed to create identity verification session")

        return {
            "verification_session_id": str(session_id),
            "client_secret": str(client_secret),
        }

    @BaseService.measure_operation("stripe_refresh_identity_status")
    def refresh_instructor_identity(self, *, user: User) -> IdentityRefreshResponse:
        """Refresh instructor identity verification status."""
        stripe_sdk = _stripe_service_module().stripe
        profile = self.instructor_repository.get_by_user_id(user.id)
        if not profile:
            raise ServiceException("Instructor profile not found", code="not_found")

        profile_id = profile.id
        self.instructor_repository.update(profile_id, bgc_in_dispute=False)
        if profile.identity_verified_at:
            return IdentityRefreshResponse(
                status="verified",
                verified=True,
                identity_name_mismatch=profile.identity_name_mismatch,
                last_error_code=None,
                last_error_reason=None,
            )

        session_id = profile.identity_verification_session_id
        if not session_id:
            return IdentityRefreshResponse(
                status="not_started",
                verified=False,
                identity_name_mismatch=profile.identity_name_mismatch,
                last_error_code=None,
                last_error_reason=None,
            )

        self._check_stripe_configured()

        try:
            session = cast(Any, stripe_sdk.identity.VerificationSession).retrieve(
                session_id,
                **self._identity_retrieve_options(),
            )
        except stripe.StripeError as exc:
            self.logger.error("Failed to retrieve identity session %s: %s", session_id, str(exc))
            return IdentityRefreshResponse(
                status="error",
                verified=False,
                identity_name_mismatch=profile.identity_name_mismatch,
                last_error_code=None,
                last_error_reason=None,
            )

        stripe_status = str(self._stripe_value(session, "status", "unknown") or "unknown")
        last_error_code, last_error_reason = self._identity_last_error(session)
        if stripe_status == "verified":
            try:
                self._persist_verified_identity(
                    profile_id=profile_id,
                    user_id=user.id,
                    session=session,
                    session_id=session_id,
                )
            except Exception as exc:
                self.logger.warning("Failed to persist verified identity: %s", exc)
                self.instructor_repository.update(
                    profile_id,
                    identity_verified_at=datetime.now(timezone.utc),
                    identity_verification_session_id=session_id,
                )
            refreshed_profile = self.instructor_repository.get_by_user_id(user.id) or profile
            return IdentityRefreshResponse(
                status="verified",
                verified=True,
                identity_name_mismatch=refreshed_profile.identity_name_mismatch,
                last_error_code=None,
                last_error_reason=None,
            )

        if stripe_status == "processing":
            last_error_code = None
            last_error_reason = None

        return IdentityRefreshResponse(
            status=stripe_status or "unknown",
            verified=False,
            identity_name_mismatch=profile.identity_name_mismatch,
            last_error_code=last_error_code,
            last_error_reason=last_error_reason,
        )

    @BaseService.measure_operation("stripe_create_identity_session")
    def create_identity_verification_session(
        self,
        *,
        user_id: str,
        return_url: str,
    ) -> Dict[str, Any]:
        """Create or resume a Stripe Identity verification session for a user."""
        stripe_sdk = _stripe_service_module().stripe
        try:
            self._check_stripe_configured()

            user: Optional[User] = self.user_repository.get_by_id(user_id)
            if not user:
                raise ServiceException("User not found for identity verification")

            profile = self.instructor_repository.get_by_user_id(user_id)
            if profile and profile.identity_verified_at:
                raise ServiceException("Identity verification already completed")

            existing_session_id = profile.identity_verification_session_id if profile else None
            if existing_session_id:
                try:
                    existing_session = cast(Any, stripe_sdk.identity.VerificationSession).retrieve(
                        existing_session_id,
                        **self._identity_retrieve_options(),
                    )
                except stripe.StripeError as exc:
                    self.logger.error(
                        "Stripe error retrieving existing identity session %s: %s",
                        existing_session_id,
                        str(exc),
                    )
                    raise ServiceException("Failed to resume identity verification") from exc

                existing_status = str(
                    self._stripe_value(existing_session, "status", "unknown") or "unknown"
                )
                if existing_status in {"requires_input", "processing"}:
                    return self._identity_session_payload(existing_session, reuse_existing=True)

                if existing_status == "verified":
                    if profile and not profile.identity_verified_at:
                        try:
                            self._persist_verified_identity(
                                profile_id=profile.id,
                                user_id=user_id,
                                session=existing_session,
                                session_id=existing_session_id,
                            )
                        except Exception as exc:
                            self.logger.warning("Failed to persist verified identity: %s", exc)
                            self.instructor_repository.update(
                                profile.id,
                                identity_verified_at=datetime.now(timezone.utc),
                                identity_verification_session_id=existing_session_id,
                            )
                    raise ServiceException("Identity verification already completed")

                if existing_status != "canceled":
                    raise ServiceException(
                        f"Identity verification session cannot be reused (status: {existing_status})"
                    )

            session = stripe_sdk.identity.VerificationSession.create(
                type="document",
                metadata={"user_id": user_id},
                options={
                    "document": {"require_live_capture": True, "require_matching_selfie": True}
                },
                return_url=return_url,
            )
            session_payload = self._identity_session_payload(session, reuse_existing=False)
            if profile:
                self.instructor_repository.update(
                    profile.id,
                    identity_verification_session_id=session_payload["verification_session_id"],
                )
            return session_payload
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating identity session: %s", exc)
            raise ServiceException(f"Failed to start identity verification: {exc}")
        except Exception as exc:
            if isinstance(exc, ServiceException):
                raise
            self.logger.error("Error creating identity session: %s", exc)
            raise ServiceException("Failed to start identity verification")
