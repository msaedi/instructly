"""Stripe connected-account persistence helpers."""

from typing import List, Optional, cast

from sqlalchemy.exc import IntegrityError
import ulid

from ...core.exceptions import RepositoryException
from ...models.payment import StripeConnectedAccount
from .mixin_base import PaymentRepositoryMixinBase


class PaymentConnectedAccountMixin(PaymentRepositoryMixinBase):
    """Connected-account queries and mutations."""

    def create_connected_account_record(
        self, instructor_profile_id: str, stripe_account_id: str, onboarding_completed: bool = False
    ) -> StripeConnectedAccount:
        """
        Create a new Stripe connected account record for an instructor.

        Args:
            instructor_profile_id: Instructor profile ID
            stripe_account_id: Stripe's connected account ID
            onboarding_completed: Whether onboarding is complete

        Returns:
            Created StripeConnectedAccount object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            account = StripeConnectedAccount(
                id=str(ulid.ULID()),
                instructor_profile_id=instructor_profile_id,
                stripe_account_id=stripe_account_id,
                onboarding_completed=onboarding_completed,
            )
            self.db.add(account)
            self.db.flush()
            return account
        except IntegrityError:
            # Let IntegrityError propagate for idempotency handling in service layer
            raise
        except Exception as e:
            self.logger.error("Failed to create connected account: %s", str(e))
            raise RepositoryException(f"Failed to create connected account: {str(e)}")

    def get_connected_account_by_instructor_id(
        self, instructor_profile_id: str
    ) -> Optional[StripeConnectedAccount]:
        """
        Get connected account by instructor profile ID.

        Args:
            instructor_profile_id: Instructor profile ID

        Returns:
            StripeConnectedAccount if found, None otherwise
        """
        try:
            account = (
                self.db.query(StripeConnectedAccount)
                .filter(StripeConnectedAccount.instructor_profile_id == instructor_profile_id)
                .first()
            )
            return cast(Optional[StripeConnectedAccount], account)
        except Exception as e:
            self.logger.error("Failed to get connected account: %s", str(e))
            raise RepositoryException(f"Failed to get connected account: {str(e)}")

    def update_onboarding_status(
        self, stripe_account_id: str, completed: bool
    ) -> Optional[StripeConnectedAccount]:
        """
        Update the onboarding status of a connected account.

        Args:
            stripe_account_id: Stripe's connected account ID
            completed: Whether onboarding is complete

        Returns:
            Updated StripeConnectedAccount if found, None otherwise
        """
        try:
            account = (
                self.db.query(StripeConnectedAccount)
                .filter(StripeConnectedAccount.stripe_account_id == stripe_account_id)
                .first()
            )
            if account:
                account.onboarding_completed = completed
                self.db.flush()
            return cast(Optional[StripeConnectedAccount], account)
        except Exception as e:
            self.logger.error("Failed to update onboarding status: %s", str(e))
            raise RepositoryException(f"Failed to update onboarding status: {str(e)}")

    def get_connected_account_by_stripe_id(
        self, stripe_account_id: str
    ) -> Optional[StripeConnectedAccount]:
        """Get connected account by Stripe connected-account ID."""
        try:
            return cast(
                Optional[StripeConnectedAccount],
                (
                    self.db.query(StripeConnectedAccount)
                    .filter(StripeConnectedAccount.stripe_account_id == stripe_account_id)
                    .first()
                ),
            )
        except Exception as e:
            self.logger.error("Failed to get connected account by stripe id: %s", str(e))
            raise RepositoryException(f"Failed to get connected account by stripe id: {str(e)}")

    def get_all_connected_accounts(self) -> List[StripeConnectedAccount]:
        """Get all Stripe connected accounts."""
        return list(self.db.query(StripeConnectedAccount).all())
