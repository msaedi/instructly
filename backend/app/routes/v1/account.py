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
import re
import secrets
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...api.dependencies.database import get_db
from ...api.dependencies.services import (
    get_account_lifecycle_service,
    get_cache_service_dep,
    get_sms_service,
)
from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.user import User
from ...repositories import RepositoryFactory
from ...schemas.account_lifecycle import AccountStatusChangeResponse, AccountStatusResponse
from ...schemas.phone import (
    PhoneUpdateRequest,
    PhoneUpdateResponse,
    PhoneVerifyConfirmRequest,
    PhoneVerifyResponse,
)
from ...services.account_lifecycle_service import AccountLifecycleService
from ...services.audit_service import AuditService
from ...services.cache_service import CacheService
from ...services.sms_service import SMSService, SMSStatus

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["account-v1"])

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
PHONE_VERIFY_TTL_SECONDS = 300
PHONE_VERIFY_RATE_LIMIT = 3
PHONE_VERIFY_WINDOW_SECONDS = 600
PHONE_CONFIRM_MAX_ATTEMPTS = 5
PHONE_CONFIRM_WINDOW_SECONDS = 300


@router.post("/suspend", response_model=AccountStatusChangeResponse)
async def suspend_account(
    request: Request,
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
        previous_status = getattr(current_user, "account_status", None)
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.suspend_instructor_account, current_user
        )
        try:
            AuditService(account_service.db).log_changes(
                action="instructor.suspend",
                resource_type="instructor",
                resource_id=current_user.id,
                old_values={"account_status": previous_status},
                new_values={"account_status": "suspended"},
                actor=current_user,
                actor_type="user",
                description="Instructor account suspended",
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for instructor suspend", exc_info=True)
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
    request: Request,
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
        previous_status = getattr(current_user, "account_status", None)
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.deactivate_instructor_account, current_user
        )
        try:
            AuditService(account_service.db).log_changes(
                action="instructor.deactivate",
                resource_type="instructor",
                resource_id=current_user.id,
                old_values={"account_status": previous_status},
                new_values={"account_status": "deactivated"},
                actor=current_user,
                actor_type="user",
                description="Instructor account deactivated",
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for instructor deactivate", exc_info=True)
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
    request: Request,
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
        previous_status = getattr(current_user, "account_status", None)
        result: Dict[str, Any] = await asyncio.to_thread(
            account_service.reactivate_instructor_account, current_user
        )
        try:
            AuditService(account_service.db).log_changes(
                action="instructor.reactivate",
                resource_type="instructor",
                resource_id=current_user.id,
                old_values={"account_status": previous_status},
                new_values={"account_status": "active"},
                actor=current_user,
                actor_type="user",
                description="Instructor account reactivated",
                request=request,
            )
        except Exception:
            logger.warning("Audit log write failed for instructor reactivate", exc_info=True)
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


@router.get("/phone", response_model=PhoneUpdateResponse)
async def get_phone_number(
    current_user: User = Depends(get_current_active_user),
) -> PhoneUpdateResponse:
    """Get the current user's phone number and verification status."""
    return PhoneUpdateResponse(
        phone_number=getattr(current_user, "phone", None),
        verified=bool(getattr(current_user, "phone_verified", False)),
    )


@router.put("/phone", response_model=PhoneUpdateResponse)
async def update_phone_number(
    request: PhoneUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> PhoneUpdateResponse:
    """Update the current user's phone number and reset verification."""
    phone_number = request.phone_number.strip()
    if not E164_PATTERN.match(phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number must be in E.164 format (+1234567890)",
        )

    def _update_phone() -> PhoneUpdateResponse:
        user_repo = RepositoryFactory.create_user_repository(db)
        user = user_repo.get_by_id(current_user.id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if getattr(user, "phone", None) != phone_number:
            updated = user_repo.update_profile(
                user.id,
                phone=phone_number,
                phone_verified=False,
            )
        else:
            updated = user

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update phone number",
            )

        return PhoneUpdateResponse(
            phone_number=getattr(updated, "phone", None),
            verified=bool(getattr(updated, "phone_verified", False)),
        )

    response = await asyncio.to_thread(_update_phone)
    await cache_service.delete(f"phone_verify:{current_user.id}")
    return response


@router.post("/phone/verify", response_model=PhoneVerifyResponse)
async def send_phone_verification(
    current_user: User = Depends(get_current_active_user),
    sms_service: SMSService = Depends(get_sms_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> PhoneVerifyResponse:
    """Send a verification code to the user's phone number."""
    phone_number = getattr(current_user, "phone", None)
    if not phone_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No phone number set")
    if not E164_PATTERN.match(phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number must be in E.164 format (+1234567890)",
        )
    if not sms_service.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service is not configured",
        )

    rate_key = f"phone_verify_rate:{current_user.id}"
    redis_client = None
    try:
        redis_client = await cache_service.get_redis_client()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to access Redis for phone verification rate limit: %s", exc)

    if redis_client is not None:
        try:
            attempts = await redis_client.incr(rate_key)
            if attempts == 1:
                await redis_client.expire(rate_key, PHONE_VERIFY_WINDOW_SECONDS)
            if attempts > PHONE_VERIFY_RATE_LIMIT:
                await redis_client.decr(rate_key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many verification requests. Try again later.",
                )
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Redis phone verification rate limit failed: %s", exc)
    else:
        cached_attempts = await cache_service.get(rate_key)
        try:
            attempts = int(cached_attempts) if cached_attempts is not None else 0
        except (TypeError, ValueError):
            attempts = 0

        if attempts >= PHONE_VERIFY_RATE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification requests. Try again later.",
            )

        await cache_service.set(
            rate_key,
            attempts + 1,
            ttl=PHONE_VERIFY_WINDOW_SECONDS,
        )

    code = str(secrets.randbelow(900000) + 100000)
    await cache_service.set(
        f"phone_verify:{current_user.id}",
        code,
        ttl=PHONE_VERIFY_TTL_SECONDS,
    )
    _result, sms_status = await sms_service.send_sms_with_status(
        phone_number,
        f"InstaInstru: Your verification code is {code}",
    )
    if sms_status != SMSStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send verification code. Please try again.",
        )

    return PhoneVerifyResponse(sent=True)


@router.post("/phone/verify/confirm", response_model=PhoneVerifyResponse)
async def confirm_phone_verification(
    request: PhoneVerifyConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> PhoneVerifyResponse:
    """Confirm phone verification with a code."""
    if not getattr(current_user, "phone", None):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No phone number set")
    code_key = f"phone_verify:{current_user.id}"
    attempts_key = f"phone_confirm_attempts:{current_user.id}"
    redis_client = None
    try:
        redis_client = await cache_service.get_redis_client()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to access Redis for phone verification attempts: %s", exc)

    attempts = 0
    if redis_client is not None:
        try:
            raw_attempts = await redis_client.get(attempts_key)
            attempts = int(raw_attempts) if raw_attempts is not None else 0
        except (TypeError, ValueError):
            attempts = 0
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Redis phone verification attempt lookup failed: %s", exc)
    else:
        cached_attempts = await cache_service.get(attempts_key)
        try:
            attempts = int(cached_attempts) if cached_attempts is not None else 0
        except (TypeError, ValueError):
            attempts = 0

    if attempts >= PHONE_CONFIRM_MAX_ATTEMPTS:
        await cache_service.delete(code_key)
        if redis_client is not None:
            await redis_client.delete(attempts_key)
        else:
            await cache_service.delete(attempts_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please request a new code.",
        )

    cached = await cache_service.get(code_key)
    cached_code = None
    if cached is not None:
        cached_code = (
            cached.decode("utf-8", errors="ignore") if isinstance(cached, bytes) else str(cached)
        )
    submitted_code = request.code.strip()
    if not cached_code or not secrets.compare_digest(cached_code, submitted_code):
        if redis_client is not None:
            try:
                next_attempts = await redis_client.incr(attempts_key)
                if next_attempts == 1:
                    await redis_client.expire(attempts_key, PHONE_CONFIRM_WINDOW_SECONDS)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("Redis phone verification attempt increment failed: %s", exc)
        else:
            await cache_service.set(
                attempts_key,
                attempts + 1,
                ttl=PHONE_CONFIRM_WINDOW_SECONDS,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    def _mark_verified() -> None:
        user_repo = RepositoryFactory.create_user_repository(db)
        user_repo.update_profile(current_user.id, phone_verified=True)

    await asyncio.to_thread(_mark_verified)
    await cache_service.delete(code_key)
    if redis_client is not None:
        await redis_client.delete(attempts_key)
    else:
        await cache_service.delete(attempts_key)

    return PhoneVerifyResponse(verified=True)


__all__ = ["router"]
