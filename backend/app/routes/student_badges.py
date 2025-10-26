# backend/app/routes/student_badges.py
"""
Student badge read APIs.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_student
from ..database import get_db
from ..models.user import User
from ..schemas.badge import StudentBadgeView
from ..services.student_badge_service import StudentBadgeService

router = APIRouter(prefix="/api/students/badges", tags=["student-badges"])


def get_student_badge_service(db: Session = Depends(get_db)) -> StudentBadgeService:
    return StudentBadgeService(db)


@router.get("", response_model=List[StudentBadgeView])
def list_student_badges(
    current_user: User = Depends(get_current_student),
    service: StudentBadgeService = Depends(get_student_badge_service),
) -> List[StudentBadgeView]:
    return service.get_student_badges(current_user.id)


@router.get("/earned", response_model=List[StudentBadgeView])
def list_earned_student_badges(
    current_user: User = Depends(get_current_student),
    service: StudentBadgeService = Depends(get_student_badge_service),
) -> List[StudentBadgeView]:
    badges = service.get_student_badges(current_user.id)
    return [badge for badge in badges if badge.get("earned")]


@router.get("/progress", response_model=List[StudentBadgeView])
def list_in_progress_student_badges(
    current_user: User = Depends(get_current_student),
    service: StudentBadgeService = Depends(get_student_badge_service),
) -> List[StudentBadgeView]:
    badges = service.get_student_badges(current_user.id)
    return [
        badge for badge in badges if not badge.get("earned") and badge.get("progress") is not None
    ]


__all__ = ["router"]
