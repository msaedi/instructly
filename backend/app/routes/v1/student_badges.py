# backend/app/routes/v1/student_badges.py
"""
V1 Student badge read APIs.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_student
from ...database import get_db
from ...models.user import User
from ...schemas.badge import StudentBadgeView
from ...services.student_badge_service import StudentBadgePayload, StudentBadgeService

# V1 router - mounted at /api/v1/students/badges
router = APIRouter(tags=["student-badges"])


def get_student_badge_service(db: Session = Depends(get_db)) -> StudentBadgeService:
    return StudentBadgeService(db)


def _to_view(payloads: List[StudentBadgePayload]) -> List[StudentBadgeView]:
    return [StudentBadgeView.model_validate(payload) for payload in payloads]


@router.get("", response_model=List[StudentBadgeView])
def list_student_badges(
    current_user: User = Depends(get_current_student),
    service: StudentBadgeService = Depends(get_student_badge_service),
) -> List[StudentBadgeView]:
    return _to_view(service.get_student_badges(current_user.id))


@router.get("/earned", response_model=List[StudentBadgeView])
def list_earned_student_badges(
    current_user: User = Depends(get_current_student),
    service: StudentBadgeService = Depends(get_student_badge_service),
) -> List[StudentBadgeView]:
    badges = _to_view(service.get_student_badges(current_user.id))
    return [badge for badge in badges if badge.earned]


@router.get("/progress", response_model=List[StudentBadgeView])
def list_in_progress_student_badges(
    current_user: User = Depends(get_current_student),
    service: StudentBadgeService = Depends(get_student_badge_service),
) -> List[StudentBadgeView]:
    badges = _to_view(service.get_student_badges(current_user.id))
    return [badge for badge in badges if not badge.earned and badge.progress is not None]


__all__ = ["router"]
