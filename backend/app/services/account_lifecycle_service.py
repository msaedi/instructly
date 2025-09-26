# backend/app/services/account_lifecycle_service.py
"""
Account Lifecycle Service for InstaInstru Platform

Handles instructor account status changes including:
- Suspension of instructor accounts
- Deactivation of instructor accounts
- Reactivation of instructor accounts
- Validation of future bookings before status changes

Students cannot change their account status - they are always active.
"""

import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from ..core.exceptions import BusinessRuleException, ValidationException
from ..models.booking import Booking
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from .base import BaseService

logger = logging.getLogger(__name__)


class AccountLifecycleService(BaseService):
    """
    Service layer for instructor account lifecycle management.

    Handles status transitions for instructor accounts with validation
    to ensure no future bookings exist before suspending or deactivating.
    """

    def __init__(self, db: Session, cache_service=None):
        """
        Initialize account lifecycle service.

        Args:
            db: Database session
            cache_service: Optional cache service for invalidation
        """
        super().__init__(db, cache=cache_service)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)
        self.user_repository = RepositoryFactory.create_base_repository(db, User)
        self.cache_service = cache_service

    @BaseService.measure_operation("check_future_bookings")
    def has_future_bookings(self, instructor: User) -> Tuple[bool, List[Booking]]:
        """
        Check if an instructor has any future bookings.

        Args:
            instructor: The instructor user to check

        Returns:
            Tuple of (has_future_bookings, list_of_future_bookings)

        Raises:
            ValidationException: If user is not an instructor
        """
        if not instructor.is_instructor:
            raise ValidationException("Only instructors can be checked for future bookings")

        self.log_operation("check_future_bookings", instructor_id=instructor.id)

        # Use repository to get future bookings that are not cancelled
        future_bookings = self.booking_repository.get_instructor_future_bookings(
            instructor_id=instructor.id, exclude_cancelled=True
        )

        return len(future_bookings) > 0, future_bookings

    @BaseService.measure_operation("suspend_account")
    def suspend_instructor_account(self, instructor: User) -> Dict[str, Any]:
        """
        Suspend an instructor account.

        Args:
            instructor: The instructor user to suspend

        Returns:
            Dict with success status and message

        Raises:
            ValidationException: If user cannot change status
            BusinessRuleException: If instructor has future bookings
        """
        self.log_operation("suspend_account", instructor_id=instructor.id)

        # Check if status change is allowed
        if not instructor.can_change_status_to("suspended"):
            if instructor.is_student:
                raise ValidationException("Students cannot change their account status")
            raise ValidationException("Invalid status transition to suspended")

        # Check for future bookings
        has_bookings, future_bookings = self.has_future_bookings(instructor)
        if has_bookings:
            raise BusinessRuleException(
                f"Cannot suspend account: instructor has {len(future_bookings)} future bookings. "
                "Please cancel all future bookings before suspending the account."
            )

        # Perform the suspension
        with self.transaction():
            self.user_repository.update(instructor.id, account_status="suspended")

        # Invalidate relevant caches
        if self.cache_service:
            self.cache_service.delete_pattern(f"instructor:{instructor.id}:*")
            self.cache_service.delete_pattern(f"availability:instructor:{instructor.id}:*")

        self.logger.info(f"Instructor {instructor.id} account suspended successfully")

        return {
            "success": True,
            "message": "Account suspended successfully",
            "previous_status": "active",
            "new_status": "suspended",
        }

    @BaseService.measure_operation("deactivate_account")
    def deactivate_instructor_account(self, instructor: User) -> Dict[str, Any]:
        """
        Permanently deactivate an instructor account.

        Args:
            instructor: The instructor user to deactivate

        Returns:
            Dict with success status and message

        Raises:
            ValidationException: If user cannot change status
            BusinessRuleException: If instructor has future bookings
        """
        self.log_operation("deactivate_account", instructor_id=instructor.id)

        # Check if status change is allowed
        if not instructor.can_change_status_to("deactivated"):
            if instructor.is_student:
                raise ValidationException("Students cannot change their account status")
            raise ValidationException("Invalid status transition to deactivated")

        # Check for future bookings
        has_bookings, future_bookings = self.has_future_bookings(instructor)
        if has_bookings:
            raise BusinessRuleException(
                f"Cannot deactivate account: instructor has {len(future_bookings)} future bookings. "
                "Please cancel all future bookings before deactivating the account."
            )

        previous_status = instructor.account_status

        # Perform the deactivation
        with self.transaction():
            self.user_repository.update(instructor.id, account_status="deactivated")

        # Invalidate relevant caches
        if self.cache_service:
            self.cache_service.delete_pattern(f"instructor:{instructor.id}:*")
            self.cache_service.delete_pattern(f"availability:instructor:{instructor.id}:*")

        self.logger.info(f"Instructor {instructor.id} account deactivated successfully")

        return {
            "success": True,
            "message": "Account deactivated successfully",
            "previous_status": previous_status,
            "new_status": "deactivated",
        }

    @BaseService.measure_operation("reactivate_account")
    def reactivate_instructor_account(self, instructor: User) -> Dict[str, Any]:
        """
        Reactivate a suspended or deactivated instructor account.

        Args:
            instructor: The instructor user to reactivate

        Returns:
            Dict with success status and message

        Raises:
            ValidationException: If user cannot change status or is already active
        """
        self.log_operation("reactivate_account", instructor_id=instructor.id)

        # Check if already active
        if instructor.is_account_active:
            raise ValidationException("Account is already active")

        # Check if status change is allowed
        if not instructor.can_change_status_to("active"):
            if instructor.is_student:
                raise ValidationException("Students cannot change their account status")
            raise ValidationException("Invalid status transition to active")

        previous_status = instructor.account_status

        # Perform the reactivation
        with self.transaction():
            self.user_repository.update(instructor.id, account_status="active")

        # Invalidate relevant caches
        if self.cache_service:
            self.cache_service.delete_pattern(f"instructor:{instructor.id}:*")
            self.cache_service.delete_pattern(f"availability:instructor:{instructor.id}:*")

        self.logger.info(f"Instructor {instructor.id} account reactivated successfully")

        return {
            "success": True,
            "message": "Account reactivated successfully",
            "previous_status": previous_status,
            "new_status": "active",
        }

    @BaseService.measure_operation("get_account_status")
    def get_account_status(self, user: User) -> Dict[str, Any]:
        """
        Get the current account status and related information.

        Args:
            user: The user to check

        Returns:
            Dict with account status information
        """
        self.log_operation("get_account_status", user_id=user.id)

        # For backwards compatibility, return the first role as 'role'
        # In RBAC, users can have multiple roles but the schema expects single role
        primary_role = user.roles[0].name if user.roles else "unknown"

        result = {
            "user_id": user.id,
            "role": primary_role,
            "account_status": user.account_status,
            "can_login": user.can_login,
            "can_receive_bookings": user.can_receive_bookings,
            "is_active": user.is_account_active,
            "is_suspended": user.is_suspended,
            "is_deactivated": user.is_deactivated,
        }

        # Add future bookings info for instructors
        if user.is_instructor:
            has_bookings, future_bookings = self.has_future_bookings(user)
            result["has_future_bookings"] = has_bookings
            result["future_bookings_count"] = len(future_bookings)
            result["can_suspend"] = not has_bookings and user.is_account_active
            result["can_deactivate"] = not has_bookings
            result["can_reactivate"] = not user.is_account_active

        return result
