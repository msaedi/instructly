"""Platform-credit persistence helpers."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy import and_, func
import ulid

from ...core.exceptions import RepositoryException
from ...models.booking_payment import BookingPayment
from ...models.payment import PaymentEvent, PlatformCredit
from .mixin_base import PaymentRepositoryMixinBase

logger = logging.getLogger(__name__)


class PaymentPlatformCreditMixin(PaymentRepositoryMixinBase):
    """Platform-credit queries and mutations."""

    def get_applied_credit_cents_for_booking(self, booking_id: str) -> int:
        """Return total cents of credits applied to the booking so far."""

        try:
            try:
                bp = (
                    self.db.query(BookingPayment)
                    .filter(BookingPayment.booking_id == booking_id)
                    .first()
                )
                if bp and bp.credits_reserved_cents:
                    return max(0, int(bp.credits_reserved_cents or 0))
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            credit_use_events = (
                self.db.query(PaymentEvent)
                .filter(
                    PaymentEvent.booking_id == booking_id,
                    PaymentEvent.event_type == "credit_used",
                )
                .all()
            )

            total_used = 0
            for event in credit_use_events:
                data = event.event_data or {}
                try:
                    total_used += max(0, int(data.get("used_cents") or 0))
                except (TypeError, ValueError):
                    continue

            if total_used > 0:
                return total_used

            fallback_events = (
                self.db.query(PaymentEvent)
                .filter(
                    PaymentEvent.booking_id == booking_id,
                    PaymentEvent.event_type == "credits_applied",
                )
                .all()
            )

            fallback_total = 0
            for event in fallback_events:
                data = event.event_data or {}
                try:
                    fallback_total += max(0, int(data.get("applied_cents") or 0))
                except (TypeError, ValueError):
                    continue

            return fallback_total
        except Exception as exc:
            self.logger.error(
                "Failed to load applied credits for booking %s: %s", booking_id, str(exc)
            )
            raise RepositoryException("Failed to compute applied credits")

    def create_platform_credit(
        self,
        user_id: str,
        amount_cents: int,
        reason: str,
        source_type: Optional[str] = None,
        source_booking_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        original_expires_at: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> PlatformCredit:
        """
        Create a platform credit for a user.

        Args:
            user_id: User to credit
            amount_cents: Amount in cents
            reason: Reason for the credit
            source_booking_id: Optional booking that generated this credit
            expires_at: Optional expiration date

        Returns:
            Created PlatformCredit object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            if expires_at is None:
                expires_at = datetime.now(timezone.utc) + timedelta(days=365)
            if original_expires_at is None:
                original_expires_at = expires_at
            credit = PlatformCredit(
                id=str(ulid.ULID()),
                user_id=user_id,
                amount_cents=amount_cents,
                reason=reason,
                source_type=source_type or reason or "manual",
                source_booking_id=source_booking_id,
                expires_at=expires_at,
                original_expires_at=original_expires_at,
                status=status or "available",
                reserved_amount_cents=0,
            )
            self.db.add(credit)
            self.db.flush()
            return credit
        except Exception as e:
            self.logger.error("Failed to create platform credit: %s", str(e))
            raise RepositoryException(f"Failed to create platform credit: {str(e)}")

    def apply_credits_for_booking(
        self, *, user_id: str, booking_id: str, amount_cents: int
    ) -> Dict[str, Any]:
        """
        Reserve available platform credits to offset an amount for a booking.

        - Uses FIFO ordering (oldest credits first)
        - Reserves credits; if a credit exceeds remaining amount, creates a remainder credit
        - Emits per-credit and summary payment events

        Returns a dict with applied amount and credit IDs used.
        """
        try:
            if amount_cents <= 0:
                return {"applied_cents": 0, "used_credit_ids": [], "remainder_credit_id": None}

            available = self.get_available_credits(user_id)
            remaining = amount_cents
            applied_total = 0
            used_ids: List[str] = []
            remainder_credit_id: Optional[str] = None
            now = datetime.now(timezone.utc)

            for credit in available:
                if remaining <= 0:
                    break

                original_credit_cents = int(credit.amount_cents or 0)
                reserve_amount = min(original_credit_cents, remaining)
                if reserve_amount <= 0:
                    continue

                local_remainder_id: Optional[str] = None
                if original_credit_cents > reserve_amount:
                    remainder = PlatformCredit(
                        id=str(ulid.ULID()),
                        user_id=user_id,
                        amount_cents=original_credit_cents - reserve_amount,
                        reason=f"Remainder of {credit.id}",
                        source_type=getattr(credit, "source_type", "manual"),
                        source_booking_id=credit.source_booking_id,
                        expires_at=credit.expires_at,
                        status="available",
                        reserved_amount_cents=0,
                    )
                    self.db.add(remainder)
                    self.db.flush()
                    remainder_credit_id = remainder.id
                    local_remainder_id = remainder.id
                    credit.amount_cents = reserve_amount
                else:
                    local_remainder_id = None

                credit.reserved_amount_cents = reserve_amount
                credit.reserved_for_booking_id = booking_id
                credit.reserved_at = now
                credit.status = "reserved"
                self.db.flush()
                used_ids.append(credit.id)

                self.create_payment_event(
                    booking_id=booking_id,
                    event_type="credit_reserved",
                    event_data={
                        "credit_id": credit.id,
                        "reserved_cents": reserve_amount,
                        "original_credit_cents": original_credit_cents,
                        "remainder_credit_id": local_remainder_id,
                    },
                )

                applied_total += reserve_amount
                remaining -= reserve_amount

            if applied_total > 0:
                self.create_payment_event(
                    booking_id=booking_id,
                    event_type="credits_applied",
                    event_data={
                        "applied_cents": applied_total,
                        "requested_cents": amount_cents,
                        "used_credit_ids": used_ids,
                        "remaining_to_charge_cents": max(amount_cents - applied_total, 0),
                    },
                )

            return {
                "applied_cents": applied_total,
                "used_credit_ids": used_ids,
                "remainder_credit_id": remainder_credit_id,
            }
        except Exception as e:
            self.logger.error("Failed to apply credits for booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to apply credits: {str(e)}")

    def get_available_credits(self, user_id: str) -> List[PlatformCredit]:
        """
        Get all available (unused, unexpired) credits for a user.

        Args:
            user_id: User ID

        Returns:
            List of available PlatformCredit objects

        Raises:
            RepositoryException: If query fails
        """
        try:
            now = datetime.now(timezone.utc)
            return cast(
                List[PlatformCredit],
                (
                    self.db.query(PlatformCredit)
                    .filter(
                        and_(
                            PlatformCredit.user_id == user_id,
                            (
                                PlatformCredit.status.is_(None)
                                | (PlatformCredit.status == "available")
                            ),
                            (
                                PlatformCredit.expires_at.is_(None)
                                | (PlatformCredit.expires_at > now)
                            ),
                        )
                    )
                    .order_by(
                        PlatformCredit.expires_at.asc().nullslast(),
                        PlatformCredit.created_at.asc(),
                        PlatformCredit.id.asc(),
                    )
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error("Failed to get available credits: %s", str(e))
            raise RepositoryException(f"Failed to get available credits: {str(e)}")

    def delete_platform_credit(self, credit_id: str) -> None:
        """Delete a platform credit by id."""

        try:
            credit = (
                self.db.query(PlatformCredit).filter(PlatformCredit.id == credit_id).one_or_none()
            )
            if not credit:
                return
            self.db.delete(credit)
            self.db.flush()
        except Exception as exc:
            self.logger.error("Failed to delete platform credit %s: %s", credit_id, str(exc))
            raise RepositoryException("Failed to delete platform credit")

    def get_credits_issued_for_source(self, booking_id: str) -> List[PlatformCredit]:
        """Return credits generated from the given booking (source)."""

        try:
            credits = (
                self.db.query(PlatformCredit)
                .filter(PlatformCredit.source_booking_id == booking_id)
                .order_by(PlatformCredit.created_at.asc())
                .all()
            )
            return cast(List[PlatformCredit], credits)
        except Exception as exc:
            self.logger.error(
                "Failed to load credits for source booking %s: %s", booking_id, str(exc)
            )
            raise RepositoryException("Failed to load source credits")

    def get_credits_used_by_booking(self, booking_id: str) -> List[Tuple[str, int]]:
        """Return list of (credit_id, used_amount_cents) for credits applied to a booking."""

        try:
            used: List[Tuple[str, int]] = []
            credits = (
                self.db.query(PlatformCredit)
                .filter(PlatformCredit.used_booking_id == booking_id)
                .all()
            )

            for credit in credits:
                try:
                    amount_int = int(credit.amount_cents or 0)
                except (TypeError, ValueError):
                    continue
                if amount_int <= 0:
                    continue
                used.append((str(credit.id), amount_int))

            if used:
                return used

            events = (
                self.db.query(PaymentEvent)
                .filter(
                    PaymentEvent.booking_id == booking_id,
                    PaymentEvent.event_type == "credit_used",
                )
                .all()
            )

            for event in events:
                data = event.event_data or {}
                credit_id = data.get("credit_id")
                used_amount = data.get("used_cents")
                if not credit_id:
                    continue
                if used_amount is None:
                    continue
                try:
                    amount_int = int(used_amount)
                except (TypeError, ValueError):
                    continue
                if amount_int <= 0:
                    continue
                used.append((str(credit_id), amount_int))
            return used
        except Exception as exc:
            self.logger.error("Failed to load credits used by booking %s: %s", booking_id, str(exc))
            raise RepositoryException("Failed to load used credits for booking")

    def get_total_available_credits(self, user_id: str) -> int:
        """
        Get total available credit amount for a user in cents.

        Args:
            user_id: User ID

        Returns:
            Total available credits in cents

        Raises:
            RepositoryException: If query fails
        """
        try:
            now = datetime.now(timezone.utc)
            result = (
                self.db.query(func.sum(PlatformCredit.amount_cents))
                .filter(
                    and_(
                        PlatformCredit.user_id == user_id,
                        (PlatformCredit.status.is_(None) | (PlatformCredit.status == "available")),
                        (PlatformCredit.expires_at.is_(None) | (PlatformCredit.expires_at > now)),
                    )
                )
                .scalar()
            )
            return result or 0
        except Exception as e:
            self.logger.error("Failed to get total available credits: %s", str(e))
            raise RepositoryException(f"Failed to get total available credits: {str(e)}")

    def mark_credit_used(self, credit_id: str, used_booking_id: str) -> PlatformCredit:
        """
        Mark a platform credit as used.

        Args:
            credit_id: Credit ID to mark as used
            used_booking_id: Booking where credit was used

        Returns:
            Updated PlatformCredit object

        Raises:
            RepositoryException: If update fails
        """
        try:
            credit_opt = cast(
                Optional[PlatformCredit],
                self.db.query(PlatformCredit).filter(PlatformCredit.id == credit_id).first(),
            )
            if credit_opt is None:
                raise RepositoryException(f"Platform credit {credit_id} not found")

            if credit_opt.used_at:
                raise RepositoryException(f"Platform credit {credit_id} already used")

            credit = credit_opt
            now = datetime.now(timezone.utc)
            credit.used_at = now
            credit.used_booking_id = used_booking_id
            credit.forfeited_at = now
            credit.status = "forfeited"
            credit.reserved_amount_cents = 0
            self.db.flush()
            return credit
        except RepositoryException:
            raise
        except Exception as e:
            self.logger.error("Failed to mark credit as used: %s", str(e))
            raise RepositoryException(f"Failed to mark credit as used: {str(e)}")
