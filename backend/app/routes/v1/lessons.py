"""
Lessons routes - API v1

Video lesson endpoints under /api/v1/lessons.
All business logic delegated to VideoService.

Endpoints:
    POST /{booking_id}/join           → Join a video lesson (authenticated participant)
    GET  /{booking_id}/video-session   → Get video session status (authenticated participant)
"""

import asyncio
import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...core.config import settings
from ...core.exceptions import DomainException
from ...database import get_db
from ...integrations.hundredms_client import FakeHundredMsClient, HundredMsClient
from ...models.user import User
from ...ratelimit.dependency import rate_limit as new_rate_limit
from ...schemas.video import VideoJoinResponse, VideoSessionStatusResponse
from ...services.video_service import VideoService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["lessons-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def get_video_service(db: Session = Depends(get_db)) -> VideoService:
    """Create VideoService with dependencies."""
    client: HundredMsClient | FakeHundredMsClient
    if not settings.hundredms_enabled:
        client = FakeHundredMsClient()
    else:
        access_key = (settings.hundredms_access_key or "").strip()
        raw_secret = settings.hundredms_app_secret
        if raw_secret is None:
            if settings.site_mode == "prod":
                logger.error("Missing HUNDREDMS_APP_SECRET in production")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Video service is temporarily unavailable",
                )
            logger.warning(
                "HUNDREDMS_APP_SECRET not configured; non-production video auth tokens will use an empty secret"
            )
            app_secret = str()
        elif hasattr(raw_secret, "get_secret_value"):
            app_secret = str(raw_secret.get_secret_value()).strip()
        else:
            app_secret = str(raw_secret).strip()
        template_id = (settings.hundredms_template_id or "").strip()
        missing: list[str] = []
        if not access_key:
            missing.append("HUNDREDMS_ACCESS_KEY")
        if not app_secret:
            missing.append("HUNDREDMS_APP_SECRET")
        if not template_id:
            missing.append("HUNDREDMS_TEMPLATE_ID")
        if missing:
            missing_fields = ", ".join(missing)
            logger.error(
                "Video service unavailable due to missing 100ms configuration: %s",
                missing_fields,
                extra={"missing_fields": missing},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Video service is temporarily unavailable",
            )

        client = HundredMsClient(
            access_key=access_key,
            app_secret=app_secret,
            base_url=settings.hundredms_base_url,
            template_id=template_id,
        )

    return VideoService(db=db, hundredms_client=client)


def handle_domain_exception(exc: DomainException) -> NoReturn:
    """Convert domain exceptions to HTTP exceptions."""
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/{booking_id}/join",
    response_model=VideoJoinResponse,
    dependencies=[Depends(new_rate_limit("video"))],
    responses={503: {"description": "Video service unavailable"}},
)
async def join_lesson(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(get_current_active_user),
    service: VideoService = Depends(get_video_service),
) -> VideoJoinResponse:
    """Join a video lesson.

    Creates the 100ms room on-demand and returns an auth token
    for the frontend video SDK.
    """
    if not settings.hundredms_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Video lessons are not currently available",
        )

    try:
        result = await asyncio.to_thread(
            service.join_lesson,
            booking_id,
            current_user.id,
        )
        return VideoJoinResponse(**result)
    except DomainException as exc:
        handle_domain_exception(exc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in join_lesson: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred joining the lesson",
        )


@router.get(
    "/{booking_id}/video-session",
    response_model=VideoSessionStatusResponse,
    dependencies=[Depends(new_rate_limit("video"))],
    responses={503: {"description": "Video service unavailable"}},
)
async def get_video_session(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(get_current_active_user),
    service: VideoService = Depends(get_video_service),
) -> VideoSessionStatusResponse:
    """Get video session status for a booking.

    Returns session timing data if a video session exists.
    """
    try:
        result = await asyncio.to_thread(
            service.get_video_session_status,
            booking_id,
            current_user.id,
        )
    except DomainException as exc:
        handle_domain_exception(exc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in get_video_session: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred retrieving the video session",
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No video session found",
        )

    return VideoSessionStatusResponse(**result)
