# backend/app/routes/v1/account.py
"""
Account Management routes - API v1

Versioned account lifecycle endpoints under /api/v1/account.
Handles instructor account suspension, deactivation, and reactivation.

Endpoints:
    POST /suspend                        → Suspend instructor account
    POST /deactivate                     → Permanently deactivate account
    POST /reactivate                     → Reactivate suspended account
    GET /status                          → Check account status
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from ...api.dependencies.auth import get_current_active_user
from ...api.dependencies.services import get_account_lifecycle_service
from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.user import User
from ...schemas.account_lifecycle import AccountStatusChangeResponse, AccountStatusResponse
from ...services.account_lifecycle_service import AccountLifecycleService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["account-v1"])


@router.post("/suspend", response_model=AccountStatusChangeResponse)
async def suspend_account(
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
) -> AccountStatusChangeResponse:
    """
    Suspend the current user's instructor account.

    Requirements:
    - User must be an instructor
    - Cannot have any future bookings
    - Suspended instructors can still login but cannot receive new bookings
    """
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can suspend their accounts",
        )

    try:
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.suspend_instructor_account, current_user
        )
        return AccountStatusChangeResponse(**result)
    except BusinessRuleException as e:
        # Extract future bookings info if available
        has_bookings, _future_bookings = await asyncio.to_thread(
            account_service.has_future_bookings, current_user
        )
        if has_bookings:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/deactivate", response_model=AccountStatusChangeResponse)
async def deactivate_account(
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
) -> AccountStatusChangeResponse:
    """
    Permanently deactivate the current user's instructor account.

    Requirements:
    - User must be an instructor
    - Cannot have any future bookings
    - Deactivated instructors cannot login or be reactivated through the API
    """
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can deactivate their accounts",
        )

    try:
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.deactivate_instructor_account, current_user
        )
        return AccountStatusChangeResponse(**result)
    except BusinessRuleException as e:
        # Extract future bookings info if available
        has_bookings, _future_bookings = await asyncio.to_thread(
            account_service.has_future_bookings, current_user
        )
        if has_bookings:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reactivate", response_model=AccountStatusChangeResponse)
async def reactivate_account(
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
) -> AccountStatusChangeResponse:
    """
    Reactivate a suspended instructor account.

    Requirements:
    - User must be an instructor
    - Account must be suspended (not deactivated)
    - Once reactivated, instructor can receive bookings again
    """
    if not current_user.is_instructor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can reactivate their accounts",
        )

    try:
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.reactivate_instructor_account, current_user
        )
        return AccountStatusChangeResponse(**result)
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/status", response_model=AccountStatusResponse)
async def check_account_status(
    current_user: User = Depends(get_current_active_user),
    account_service: AccountLifecycleService = Depends(get_account_lifecycle_service),
) -> AccountStatusResponse:
    """
    Check the current account status and available status change options.

    Returns:
    - Current account status
    - Whether the instructor can login
    - Whether the instructor can receive bookings
    - Available status change options based on current state and future bookings
    """
    try:
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.get_account_status, current_user
        )
        return AccountStatusResponse(**result)
    except Exception as e:
        logger.error(f"Error checking account status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check account status",
        )


__all__ = ["router"]
