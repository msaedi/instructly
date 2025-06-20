# backend/app/routes/instructors.py
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models.user import User, UserRole
from ..schemas.instructor import InstructorProfileCreate, InstructorProfileResponse, InstructorProfileUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instructors", tags=["instructors"])


async def get_current_active_user(
    current_user_email: str = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/", response_model=List[InstructorProfileResponse])
async def get_all_instructors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all instructor profiles with active services only."""
    # Import here to avoid circular imports
    from ..services.instructor_service import InstructorService

    instructor_service = InstructorService(db)
    profiles = instructor_service.get_all_instructors(skip=skip, limit=limit)
    return profiles


@router.post(
    "/profile",
    response_model=InstructorProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_instructor_profile(
    profile: InstructorProfileCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new instructor profile."""
    from ..services.instructor_service import InstructorService

    instructor_service = InstructorService(db)

    try:
        profile_data = instructor_service.create_instructor_profile(user=current_user, profile_data=profile)
        return profile_data
    except Exception as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise


@router.get("/profile", response_model=InstructorProfileResponse)
async def get_my_profile(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Get current instructor's profile."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access profiles",
        )

    from ..services.instructor_service import InstructorService

    instructor_service = InstructorService(db)

    try:
        profile_data = instructor_service.get_instructor_profile(current_user.id)
        return profile_data
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise


@router.put("/profile", response_model=InstructorProfileResponse)
async def update_profile(
    profile_update: InstructorProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update instructor profile with soft delete support."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can update profiles",
        )

    from ..services.instructor_service import InstructorService

    instructor_service = InstructorService(db)

    try:
        profile_data = instructor_service.update_instructor_profile(user_id=current_user.id, update_data=profile_update)
        return profile_data
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instructor_profile(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """Delete instructor profile and revert to student role."""
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can delete their profiles",
        )

    from ..services.instructor_service import InstructorService

    instructor_service = InstructorService(db)

    try:
        instructor_service.delete_instructor_profile(current_user.id)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise


@router.get("/{instructor_id}", response_model=InstructorProfileResponse)
async def get_instructor_profile(instructor_id: int, db: Session = Depends(get_db)):
    """Get a specific instructor's profile by user ID."""
    from ..services.instructor_service import InstructorService

    instructor_service = InstructorService(db)

    try:
        profile_data = instructor_service.get_instructor_profile(instructor_id)
        return profile_data
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")
        raise
