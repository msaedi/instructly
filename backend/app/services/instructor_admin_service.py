"""Admin instructor actions for MCP workflows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictException,
    MCPTokenError,
    NotFoundException,
    ValidationException,
)
from app.models.booking import Booking
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_instructor_actions import (
    CommissionAction,
    CommissionTier,
    InstructorState,
    PayoutHoldAction,
    PayoutHoldResponse,
    SuspendExecuteResponse,
    SuspendPreviewResponse,
    UnsuspendResponse,
    UpdateCommissionExecuteResponse,
    UpdateCommissionPreviewResponse,
    VerificationType,
    VerifyOverrideResponse,
)
from app.services.audit_service import AuditService
from app.services.base import BaseService
from app.services.booking_service import BookingService
from app.services.config_service import DEFAULT_PRICING_CONFIG, ConfigService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.notification_service import NotificationService
from app.services.search.cache_invalidation import invalidate_on_instructor_profile_change

logger = logging.getLogger(__name__)

_DECIMAL_00 = Decimal("0.00")
_DECIMAL_RATE = Decimal("0.0001")


def _cents_to_decimal(value: int | None) -> Decimal:
    if value is None:
        return _DECIMAL_00
    return (Decimal(value) / Decimal("100")).quantize(Decimal("0.01"))


def _normalize_rate(value: Decimal | float | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0.0").quantize(_DECIMAL_RATE)
    rate = Decimal(str(value))
    if rate > 1:
        rate = rate / Decimal("100")
    return rate.quantize(_DECIMAL_RATE)


def _booking_amount(booking: Booking) -> Decimal:
    if booking.total_price is not None:
        return Decimal(str(booking.total_price)).quantize(Decimal("0.01"))
    if booking.hourly_rate is None or not booking.duration_minutes:
        return _DECIMAL_00
    hourly = Decimal(str(booking.hourly_rate))
    duration = Decimal(int(booking.duration_minutes))
    total = (hourly * duration / Decimal("60")).quantize(Decimal("0.01"))
    return total


class InstructorAdminService(BaseService):
    """Admin instructor actions with preview/execute guardrails."""

    CONFIRM_TOKEN_TTL = timedelta(minutes=5)

    def __init__(
        self,
        db: Session,
        *,
        booking_service: BookingService | None = None,
        confirm_service: MCPConfirmTokenService | None = None,
        idempotency_service: MCPIdempotencyService | None = None,
        notification_service: NotificationService | None = None,
        audit_service: AuditService | None = None,
        config_service: ConfigService | None = None,
    ) -> None:
        super().__init__(db)
        self.profile_repo = RepositoryFactory.create_instructor_profile_repository(db)
        self.user_repo = RepositoryFactory.create_user_repository(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.conversation_repo = RepositoryFactory.create_conversation_repository(db)
        self.confirm_service = confirm_service or MCPConfirmTokenService(db)
        self.idempotency_service = idempotency_service or MCPIdempotencyService(db)
        self.notification_service = notification_service or NotificationService(db)
        self.booking_service = booking_service or BookingService(
            db,
            notification_service=self.notification_service,
        )
        self.audit_service = audit_service or AuditService(db)
        self.config_service = config_service or ConfigService(db)

    def _load_instructor(self, instructor_id: str) -> tuple[User, InstructorProfile]:
        profile = self.profile_repo.get_by_user_id(instructor_id)
        if profile:
            user = self.user_repo.get_by_id(profile.user_id)
            if not user:
                raise NotFoundException("Instructor not found")
            return user, profile

        profile = self.profile_repo.get_by_id_join_user(instructor_id)
        if profile and profile.user:
            return profile.user, profile

        if "@" in instructor_id:
            user = self.user_repo.get_by_email(instructor_id)
            if user:
                profile = self.profile_repo.get_by_user_id(user.id)
                if profile:
                    return user, profile

        raise NotFoundException("Instructor not found")

    def _ensure_instructor(self, user: User) -> None:
        if not user.is_instructor:
            raise ValidationException("User is not an instructor")

    def _is_verified(self, profile: InstructorProfile) -> bool:
        identity_ok = bool(getattr(profile, "identity_verified_at", None))
        bgc_ok = (getattr(profile, "bgc_status", "") or "").lower() == "passed"
        connected = self.payment_repo.get_connected_account_by_instructor_id(profile.id)
        connect_ok = bool(connected and getattr(connected, "onboarding_completed", False))
        return bool(identity_ok and bgc_ok and connect_ok)

    def _tier_mapping(self) -> dict[str, Decimal]:
        pricing_config, _ = self.config_service.get_pricing_config()
        tiers = pricing_config.get("instructor_tiers") or DEFAULT_PRICING_CONFIG.get(
            "instructor_tiers", []
        )
        tiers = sorted(tiers, key=lambda tier: tier.get("min", 0))
        tier_names = ["entry", "growth", "pro"]
        mapping: dict[str, Decimal] = {}
        for idx, tier in enumerate(tiers):
            if idx >= len(tier_names):
                break
            mapping[tier_names[idx]] = _normalize_rate(tier.get("pct", 0))
        mapping["founding"] = _normalize_rate(
            pricing_config.get(
                "founding_instructor_rate_pct",
                DEFAULT_PRICING_CONFIG.get("founding_instructor_rate_pct", 0),
            )
        )
        return mapping

    def _resolve_current_rate(self, profile: InstructorProfile) -> Decimal:
        if getattr(profile, "is_founding_instructor", False):
            return self._tier_mapping().get("founding", _DECIMAL_00)

        override_pct = getattr(profile, "commission_override_pct", None)
        override_until = getattr(profile, "commission_override_until", None)
        now = datetime.now(timezone.utc)
        if override_pct is not None and (override_until is None or override_until >= now):
            return _normalize_rate(override_pct)

        if profile.current_tier_pct is not None:
            return _normalize_rate(profile.current_tier_pct)
        return self._tier_mapping().get("entry", _DECIMAL_00)

    def _resolve_current_tier(self, profile: InstructorProfile) -> str:
        if getattr(profile, "is_founding_instructor", False):
            return "founding"
        override_pct = getattr(profile, "commission_override_pct", None)
        override_until = getattr(profile, "commission_override_until", None)
        now = datetime.now(timezone.utc)
        if override_pct is not None and (override_until is None or override_until >= now):
            return "temporary_discount"
        rate = self._resolve_current_rate(profile)
        for name, tier_rate in self._tier_mapping().items():
            if name == "founding":
                continue
            if abs(rate - tier_rate) <= _DECIMAL_RATE:
                return name
        return "custom"

    def _pending_payouts(
        self, instructor_id: str, profile: InstructorProfile
    ) -> tuple[int, Decimal]:
        bookings = self.booking_repo.get_instructor_completed_authorized_bookings(instructor_id)
        total_cents = 0
        rate = self._resolve_current_rate(profile)
        for booking in bookings:
            payment = booking.payment_intent
            payout_cents = None
            if payment and payment.instructor_payout_cents is not None:
                try:
                    payout_cents = int(payment.instructor_payout_cents)
                except (TypeError, ValueError):
                    payout_cents = None
            if payout_cents is None and payment and payment.amount is not None:
                try:
                    payout_cents = int(payment.amount) - int(payment.application_fee or 0)
                except (TypeError, ValueError):
                    payout_cents = None
            if payout_cents is None:
                gross_cents = int(
                    (_booking_amount(booking) * Decimal("100")).quantize(Decimal("1"))
                )
                payout_cents = int(
                    (Decimal(gross_cents) * (Decimal("1.0") - rate)).quantize(Decimal("1"))
                )
            total_cents += max(0, int(payout_cents or 0))
        return len(bookings), _cents_to_decimal(total_cents)

    def _recent_volume(self, instructor_id: str) -> Decimal:
        window_start = datetime.now(timezone.utc) - timedelta(days=30)
        total = self.booking_repo.sum_instructor_completed_total_price_since(
            instructor_id, window_start
        )
        return Decimal(str(total)).quantize(Decimal("0.01"))

    @BaseService.measure_operation("mcp_instructor_actions.preview_suspend")
    def preview_suspend(
        self,
        *,
        instructor_id: str,
        reason_code: str,
        note: str,
        notify_instructor: bool,
        cancel_pending_bookings: bool,
        actor_id: str,
    ) -> SuspendPreviewResponse:
        user, profile = self._load_instructor(instructor_id)
        self._ensure_instructor(user)

        current_state = InstructorState(
            account_status=user.account_status,
            is_verified=self._is_verified(profile),
            is_founding=bool(getattr(profile, "is_founding_instructor", False)),
        )

        eligible = True
        ineligible_reason = None
        if user.account_status == "suspended":
            eligible = False
            ineligible_reason = "Already suspended"
        elif user.account_status == "deactivated":
            eligible = False
            ineligible_reason = "Account deactivated"

        pending_bookings = self.booking_repo.get_instructor_future_bookings(
            instructor_id=user.id, exclude_cancelled=True
        )
        pending_value = sum((_booking_amount(b) for b in pending_bookings), _DECIMAL_00)

        pending_payouts_count, pending_payout_amount = self._pending_payouts(user.id, profile)
        active_conversations = int(self.conversation_repo.count_for_user(user.id) or 0)

        warnings: list[str] = []
        if pending_bookings:
            warnings.append(
                f"Instructor has {len(pending_bookings)} pending bookings totaling ${pending_value}"
            )
        if pending_payouts_count:
            warnings.append(
                f"Instructor has {pending_payouts_count} pending payouts totaling ${pending_payout_amount}"
            )
        if active_conversations:
            warnings.append(f"Instructor has {active_conversations} active conversations")
        if pending_bookings and not cancel_pending_bookings:
            warnings.append("Pending bookings will remain active")

        will_suspend = eligible
        will_cancel_bookings = bool(
            eligible and cancel_pending_bookings and len(pending_bookings) > 0
        )

        confirm_token = None
        idempotency_key = None
        if eligible:
            idempotency_key = str(uuid4())
            payload = {
                "instructor_id": instructor_id,
                "reason_code": reason_code,
                "note": note,
                "notify_instructor": notify_instructor,
                "cancel_pending_bookings": cancel_pending_bookings,
                "idempotency_key": idempotency_key,
            }
            confirm_token, _expires_at = self.confirm_service.generate_token(
                payload,
                actor_id=actor_id,
                ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() / 60),
            )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_SUSPEND_PREVIEW",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "reason_code": reason_code,
                "eligible": eligible,
                "cancel_pending_bookings": cancel_pending_bookings,
            },
        )

        return SuspendPreviewResponse(
            eligible=eligible,
            ineligible_reason=ineligible_reason,
            current_state=current_state,
            pending_bookings_count=len(pending_bookings),
            pending_bookings_value=pending_value,
            pending_payout_amount=pending_payout_amount,
            active_conversations=active_conversations,
            will_suspend=will_suspend,
            will_cancel_bookings=will_cancel_bookings,
            will_refund_students=will_cancel_bookings,
            will_hold_payouts=eligible,
            will_notify_instructor=bool(eligible and notify_instructor),
            will_notify_affected_students=will_cancel_bookings,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    @BaseService.measure_operation("mcp_instructor_actions.execute_suspend")
    async def execute_suspend(
        self,
        *,
        instructor_id: str,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> SuspendExecuteResponse:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError:
            raise

        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")

        self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)

        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        token_instructor_id = str(payload.get("instructor_id"))
        if instructor_id and token_instructor_id != instructor_id:
            raise ValidationException("Instructor ID mismatch", code="INSTRUCTOR_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_instructor.suspend"
            )
        except Exception as exc:
            logger.error("Suspend idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return SuspendExecuteResponse.model_validate(cached)

        user, profile = self._load_instructor(token_instructor_id)
        self._ensure_instructor(user)

        if user.account_status == "suspended":
            raise ValidationException("Instructor already suspended", code="ALREADY_SUSPENDED")

        previous_status = user.account_status
        reason_code = str(payload.get("reason_code"))
        note = str(payload.get("note"))
        cancel_pending = bool(payload.get("cancel_pending_bookings", True))
        notify_instructor = bool(payload.get("notify_instructor", True))

        bookings_cancelled = 0
        refunds_issued = 0
        total_refunded_cents = 0
        error: str | None = None

        if cancel_pending:
            pending_bookings = await asyncio.to_thread(
                self.booking_repo.get_instructor_future_bookings,
                instructor_id=user.id,
                exclude_cancelled=True,
            )
            for booking in pending_bookings:
                try:
                    await asyncio.to_thread(
                        self.booking_service.cancel_booking,
                        booking_id=booking.id,
                        user=user,
                        reason=reason_code,
                    )
                    refreshed = await asyncio.to_thread(self.booking_repo.get_by_id, booking.id)
                    bookings_cancelled += 1
                    refunded = getattr(refreshed, "refunded_to_card_amount", None)
                    if refunded:
                        refunds_issued += 1
                        total_refunded_cents += int(refunded)
                except Exception as exc:
                    logger.error("Failed to cancel booking %s", booking.id, exc_info=exc)
                    error = "cancel_pending_bookings_failed"

        now = datetime.now(timezone.utc)
        with self.transaction():
            user.account_status = "suspended"
            profile.is_live = False
            profile.payout_hold = True
            profile.payout_hold_reason = reason_code
            profile.payout_hold_at = now
            profile.payout_hold_released_at = None

        invalidated = await asyncio.to_thread(
            self.user_repo.invalidate_all_tokens,
            user.id,
            trigger="suspension",
        )
        if not invalidated:
            logger.warning(
                "Instructor suspend succeeded but token invalidation helper returned false for %s",
                user.id,
            )

        invalidate_on_instructor_profile_change(user.id)

        notifications_sent = []
        if cancel_pending:
            notifications_sent.append("students_booking_cancelled")
        if notify_instructor:
            notifications_sent.append("instructor_notified")

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_SUSPEND_EXECUTE",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "reason_code": reason_code,
                "note": note,
                "cancel_pending_bookings": cancel_pending,
                "idempotency_key": idempotency_key,
            },
            status="failed" if error else "success",
            error_message=error,
        )

        response = SuspendExecuteResponse(
            success=error is None,
            error=error,
            instructor_id=user.id,
            previous_status=previous_status,
            new_status=user.account_status,
            bookings_cancelled=bookings_cancelled,
            refunds_issued=refunds_issued,
            total_refunded=_cents_to_decimal(total_refunded_cents),
            notifications_sent=notifications_sent,
            audit_id=audit_id,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )
        return response

    @BaseService.measure_operation("mcp_instructor_actions.unsuspend")
    def unsuspend(
        self,
        *,
        instructor_id: str,
        reason: str,
        restore_visibility: bool,
        actor_id: str,
    ) -> UnsuspendResponse:
        user, profile = self._load_instructor(instructor_id)
        self._ensure_instructor(user)

        if user.account_status != "suspended":
            raise ValidationException("Instructor is not suspended", code="NOT_SUSPENDED")

        previous_status = user.account_status
        payout_hold_released = bool(profile.payout_hold)
        visibility_restored = False

        with self.transaction():
            user.account_status = "active"
            if restore_visibility:
                profile.is_live = True
                visibility_restored = True
            profile.payout_hold = False
            profile.payout_hold_reason = None
            profile.payout_hold_released_at = datetime.now(timezone.utc)

        invalidate_on_instructor_profile_change(user.id)

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_UNSUSPEND",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "reason": reason,
                "restore_visibility": restore_visibility,
            },
        )

        return UnsuspendResponse(
            success=True,
            instructor_id=user.id,
            previous_status=previous_status,
            new_status=user.account_status,
            visibility_restored=visibility_restored,
            payout_hold_released=payout_hold_released,
            audit_id=audit_id,
        )

    @BaseService.measure_operation("mcp_instructor_actions.verify_override")
    def verify_override(
        self,
        *,
        instructor_id: str,
        verification_type: VerificationType,
        reason: str,
        evidence: str | None,
        actor_id: str,
    ) -> VerifyOverrideResponse:
        user, profile = self._load_instructor(instructor_id)
        self._ensure_instructor(user)

        connected = self.payment_repo.get_connected_account_by_instructor_id(profile.id)
        previous_status = {
            "identity": bool(getattr(profile, "identity_verified_at", None)),
            "background_check": (getattr(profile, "bgc_status", "") or "").lower() == "passed",
            "payment_setup": bool(connected and connected.onboarding_completed),
        }

        if verification_type in {VerificationType.PAYMENT_SETUP, VerificationType.FULL} and not (
            connected and connected.stripe_account_id
        ):
            raise ValidationException(
                "Instructor has no connected account", code="NO_CONNECTED_ACCOUNT"
            )

        now = datetime.now(timezone.utc)
        with self.transaction():
            if verification_type in {VerificationType.IDENTITY, VerificationType.FULL}:
                profile.identity_verified_at = now
                profile.identity_verification_session_id = "manual_override"
            if verification_type in {VerificationType.BACKGROUND_CHECK, VerificationType.FULL}:
                profile.bgc_status = "passed"
                profile.bgc_completed_at = now
                profile.bgc_report_result = "manual_override"
            if verification_type in {VerificationType.PAYMENT_SETUP, VerificationType.FULL}:
                if connected:
                    connected.onboarding_completed = True

        new_status = {
            "identity": bool(getattr(profile, "identity_verified_at", None)),
            "background_check": (getattr(profile, "bgc_status", "") or "").lower() == "passed",
            "payment_setup": bool(connected and connected.onboarding_completed),
        }

        now_fully_verified = all(new_status.values())
        search_eligible = bool(now_fully_verified and profile.is_live and user.is_account_active)

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_VERIFY_OVERRIDE",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "verification_type": verification_type.value,
                "reason": reason,
                "evidence": evidence,
            },
        )

        return VerifyOverrideResponse(
            success=True,
            instructor_id=user.id,
            verification_type=verification_type.value,
            previous_status=previous_status,
            new_status=new_status,
            now_fully_verified=now_fully_verified,
            search_eligible=search_eligible,
            audit_id=audit_id,
        )

    @BaseService.measure_operation("mcp_instructor_actions.preview_update_commission")
    def preview_update_commission(
        self,
        *,
        instructor_id: str,
        action: CommissionAction,
        tier: CommissionTier | None,
        temporary_rate: Decimal | None,
        temporary_until: datetime | None,
        reason: str,
        actor_id: str,
    ) -> UpdateCommissionPreviewResponse:
        user, profile = self._load_instructor(instructor_id)
        self._ensure_instructor(user)

        mapping = self._tier_mapping()
        current_rate = self._resolve_current_rate(profile)
        current_tier = self._resolve_current_tier(profile)
        is_founding = bool(getattr(profile, "is_founding_instructor", False))

        eligible = True
        ineligible_reason = None
        warnings: list[str] = []

        new_tier = current_tier
        new_rate = current_rate
        will_be_founding = is_founding

        if action == CommissionAction.SET_TIER:
            if tier is None:
                eligible = False
                ineligible_reason = "Tier required"
            elif is_founding:
                eligible = False
                ineligible_reason = "Founding instructors are immune to tier changes"
            else:
                new_tier = tier.value
                new_rate = mapping.get(tier.value, current_rate)
        elif action == CommissionAction.GRANT_FOUNDING:
            if is_founding:
                eligible = False
                ineligible_reason = "Already a founding instructor"
            else:
                pricing_config, _ = self.config_service.get_pricing_config()
                cap_raw = pricing_config.get("founding_instructor_cap", 100)
                try:
                    cap = int(cap_raw)
                except (TypeError, ValueError):
                    cap = 100
                used = self.profile_repo.count_founding_instructors()
                if used >= cap:
                    eligible = False
                    ineligible_reason = "Founding cap reached"
                    warnings.append("Founding cap reached - cannot grant")
                else:
                    new_tier = "founding"
                    new_rate = mapping.get("founding", current_rate)
                    will_be_founding = True
        elif action == CommissionAction.REVOKE_FOUNDING:
            if not is_founding:
                eligible = False
                ineligible_reason = "Instructor is not founding"
            else:
                new_tier = "entry"
                new_rate = mapping.get("entry", current_rate)
                will_be_founding = False
                warnings.append("Founding revoked - defaulting to entry tier")
        elif action == CommissionAction.TEMPORARY_DISCOUNT:
            if temporary_rate is None:
                eligible = False
                ineligible_reason = "temporary_rate required"
            elif is_founding:
                eligible = False
                ineligible_reason = "Founding instructors cannot receive discounts"
            else:
                new_rate = _normalize_rate(temporary_rate)
                new_tier = "temporary_discount"
                if temporary_until and temporary_until < datetime.now(timezone.utc):
                    eligible = False
                    ineligible_reason = "temporary_until must be in the future"

        if eligible and new_rate < _DECIMAL_00:
            eligible = False
            ineligible_reason = "Invalid rate"

        rate_change = (new_rate - current_rate).quantize(_DECIMAL_RATE)
        volume = self._recent_volume(user.id)
        estimated_impact = (volume * (current_rate - new_rate)).quantize(Decimal("0.01"))

        confirm_token = None
        idempotency_key = None
        if eligible:
            idempotency_key = str(uuid4())
            payload = {
                "instructor_id": user.id,
                "action": action.value,
                "tier": tier.value if tier else None,
                "temporary_rate": str(temporary_rate) if temporary_rate is not None else None,
                "temporary_until": temporary_until,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
            confirm_token, _expires_at = self.confirm_service.generate_token(
                payload,
                actor_id=actor_id,
                ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() / 60),
            )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_COMMISSION_PREVIEW",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "action": action.value,
                "tier": tier.value if tier else None,
                "eligible": eligible,
            },
        )

        return UpdateCommissionPreviewResponse(
            eligible=eligible,
            ineligible_reason=ineligible_reason,
            current_tier=current_tier,
            current_rate=current_rate,
            is_founding=is_founding,
            new_tier=new_tier,
            new_rate=new_rate,
            will_be_founding=will_be_founding,
            rate_change=rate_change,
            estimated_monthly_impact=estimated_impact,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    @BaseService.measure_operation("mcp_instructor_actions.execute_update_commission")
    async def execute_update_commission(
        self,
        *,
        instructor_id: str,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> UpdateCommissionExecuteResponse:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError:
            raise

        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")

        self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)

        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        token_instructor_id = str(payload.get("instructor_id"))
        if instructor_id and token_instructor_id != instructor_id:
            raise ValidationException("Instructor ID mismatch", code="INSTRUCTOR_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_instructor.update_commission"
            )
        except Exception as exc:
            logger.error("Update commission idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return UpdateCommissionExecuteResponse.model_validate(cached)

        user, profile = self._load_instructor(token_instructor_id)
        self._ensure_instructor(user)

        mapping = self._tier_mapping()
        previous_rate = self._resolve_current_rate(profile)
        previous_tier = self._resolve_current_tier(profile)
        founding_before = bool(getattr(profile, "is_founding_instructor", False))

        action = CommissionAction(str(payload.get("action")))
        tier_value = payload.get("tier")
        temporary_rate_raw = payload.get("temporary_rate")
        temporary_until_raw = payload.get("temporary_until")

        error: str | None = None
        new_tier = previous_tier
        new_rate = previous_rate
        founding_after = founding_before

        if action == CommissionAction.SET_TIER:
            if not tier_value:
                raise ValidationException("Tier required", code="TIER_REQUIRED")
            if founding_before:
                raise ValidationException("Founding instructors are immune", code="FOUNDING_IMMUNE")
            new_tier = str(tier_value)
            new_rate = mapping.get(new_tier, previous_rate)
            with self.transaction():
                profile.current_tier_pct = (new_rate * Decimal("100")).quantize(Decimal("0.01"))
                profile.last_tier_eval_at = datetime.now(timezone.utc)
                profile.commission_override_pct = None
                profile.commission_override_until = None
        elif action == CommissionAction.GRANT_FOUNDING:
            if founding_before:
                raise ValidationException("Already founding", code="ALREADY_FOUNDING")
            pricing_config, _ = self.config_service.get_pricing_config()
            cap_raw = pricing_config.get("founding_instructor_cap", 100)
            try:
                cap = int(cap_raw)
            except (TypeError, ValueError):
                cap = 100
            granted, _count = await asyncio.to_thread(
                self.profile_repo.try_claim_founding_status, profile.id, cap
            )
            if not granted:
                raise ValidationException("Founding cap reached", code="FOUNDING_CAP_REACHED")
            founding_after = True
            new_tier = "founding"
            new_rate = mapping.get("founding", previous_rate)
            with self.transaction():
                profile.commission_override_pct = None
                profile.commission_override_until = None
        elif action == CommissionAction.REVOKE_FOUNDING:
            if not founding_before:
                raise ValidationException("Not founding", code="NOT_FOUNDING")
            new_tier = "entry"
            new_rate = mapping.get("entry", previous_rate)
            with self.transaction():
                profile.is_founding_instructor = False
                profile.founding_granted_at = None
                profile.current_tier_pct = (new_rate * Decimal("100")).quantize(Decimal("0.01"))
                profile.last_tier_eval_at = datetime.now(timezone.utc)
                profile.commission_override_pct = None
                profile.commission_override_until = None
            founding_after = False
        elif action == CommissionAction.TEMPORARY_DISCOUNT:
            if temporary_rate_raw is None:
                raise ValidationException("temporary_rate required", code="TEMP_RATE_REQUIRED")
            if founding_before:
                raise ValidationException(
                    "Founding instructors cannot receive discounts",
                    code="FOUNDING_IMMUNE",
                )
            new_rate = _normalize_rate(temporary_rate_raw)
            new_tier = "temporary_discount"
            temp_until = None
            if temporary_until_raw:
                try:
                    temp_until = datetime.fromisoformat(str(temporary_until_raw))
                except ValueError:
                    temp_until = None
            with self.transaction():
                profile.current_tier_pct = (new_rate * Decimal("100")).quantize(Decimal("0.01"))
                profile.last_tier_eval_at = datetime.now(timezone.utc)
                profile.commission_override_pct = (new_rate * Decimal("100")).quantize(
                    Decimal("0.01")
                )
                profile.commission_override_until = temp_until

        invalidate_on_instructor_profile_change(user.id)

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_COMMISSION_EXECUTE",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "action": action.value,
                "tier": tier_value,
                "idempotency_key": idempotency_key,
            },
            status="failed" if error else "success",
            error_message=error,
        )

        response = UpdateCommissionExecuteResponse(
            success=error is None,
            error=error,
            instructor_id=user.id,
            previous_tier=previous_tier,
            new_tier=new_tier,
            previous_rate=previous_rate,
            new_rate=new_rate,
            founding_status_changed=founding_before != founding_after,
            audit_id=audit_id,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )
        return response

    @BaseService.measure_operation("mcp_instructor_actions.payout_hold")
    def payout_hold(
        self,
        *,
        instructor_id: str,
        action: PayoutHoldAction,
        reason: str,
        actor_id: str,
    ) -> PayoutHoldResponse:
        user, profile = self._load_instructor(instructor_id)
        self._ensure_instructor(user)

        now = datetime.now(timezone.utc)
        with self.transaction():
            if action == PayoutHoldAction.HOLD:
                profile.payout_hold = True
                profile.payout_hold_reason = reason
                profile.payout_hold_at = now
                profile.payout_hold_released_at = None
            else:
                profile.payout_hold = False
                profile.payout_hold_reason = None
                profile.payout_hold_released_at = now

        pending_count, pending_amount = self._pending_payouts(user.id, profile)
        held_amount = pending_amount if profile.payout_hold else _DECIMAL_00

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="INSTRUCTOR_PAYOUT_HOLD",
            resource_type="instructor",
            resource_id=user.id,
            metadata={
                "action": action.value,
                "reason": reason,
            },
        )

        return PayoutHoldResponse(
            success=True,
            instructor_id=user.id,
            action=action.value,
            held_amount=held_amount,
            pending_payouts=pending_count,
            audit_id=audit_id,
        )
