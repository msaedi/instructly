from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User, UserRole
from ..schemas.instructor import InstructorProfileCreate, InstructorProfileResponse, InstructorProfileUpdate


async def get_current_active_user(
    current_user_email: str = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.get("/", response_model=List[InstructorProfileResponse])
async def get_all_instructors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    instructors = (
        db.query(InstructorProfile).options(joinedload(InstructorProfile.user)).offset(skip).limit(limit).all()
    )
    return instructors


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
    # Check if profile already exists
    existing_profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == current_user.id).first()

    if existing_profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile already exists")

    # Create the instructor profile (without services)
    profile_data = profile.model_dump(exclude={"services"})
    db_profile = InstructorProfile(user_id=current_user.id, **profile_data)

    db.add(db_profile)
    db.flush()  # Flush to get the profile ID

    # Create services
    for service_data in profile.services:
        db_service = Service(instructor_profile_id=db_profile.id, **service_data.model_dump())
        db.add(db_service)

    # Update user role to instructor
    current_user.role = UserRole.INSTRUCTOR

    db.commit()
    db.refresh(db_profile)
    db_profile = (
        db.query(InstructorProfile)
        .options(joinedload(InstructorProfile.user))
        .options(joinedload(InstructorProfile.services))
        .filter(InstructorProfile.id == db_profile.id)
        .first()
    )
    return db_profile


@router.get("/profile", response_model=InstructorProfileResponse)
async def get_my_profile(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if current_user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access profiles",
        )

    profile = (
        db.query(InstructorProfile)
        .options(joinedload(InstructorProfile.user))
        .options(joinedload(InstructorProfile.services))
        .filter(InstructorProfile.user_id == current_user.id)
        .first()
    )

    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    return profile


@router.put("/profile", response_model=InstructorProfileResponse)
async def update_profile(
    profile_update: InstructorProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can update profiles",
        )

    db_profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == current_user.id).first()

    if not db_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    # Update basic profile fields
    update_data = profile_update.model_dump(exclude={"services"}, exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_profile, field, value)

    # Handle services update if provided
    if profile_update.services is not None:
        # TEMPORARY FIX: Only update services, don't delete and recreate
        # Get existing services
        existing_services = {s.skill.lower(): s for s in db_profile.services}
        {s.skill.lower() for s in profile_update.services}

        # Update existing services
        for service_data in profile_update.services:
            skill_lower = service_data.skill.lower()
            if skill_lower in existing_services:
                # Update existing service
                service = existing_services[skill_lower]
                for field, value in service_data.model_dump().items():
                    setattr(service, field, value)
            else:
                # Create new service
                db_service = Service(instructor_profile_id=db_profile.id, **service_data.model_dump())
                db.add(db_service)

        # For now, DON'T delete services that aren't in the update
        # This prevents the foreign key error
        # We'll handle this properly with soft delete

    db.commit()
    db.refresh(db_profile)
    db_profile = (
        db.query(InstructorProfile)
        .options(joinedload(InstructorProfile.user))
        .options(joinedload(InstructorProfile.services))
        .filter(InstructorProfile.id == db_profile.id)
        .first()
    )
    return db_profile


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instructor_profile(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """
    Delete instructor profile and revert user to student role.
    This will also handle cascading deletes for related data.
    """
    if current_user.role != UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can delete their profiles",
        )

    # Get the instructor profile
    db_profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == current_user.id).first()

    if not db_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    # Delete the profile (services will be cascade deleted due to relationship)
    db.delete(db_profile)

    # Change user role back to student
    current_user.role = UserRole.STUDENT

    db.commit()

    return {"message": "Instructor profile deleted successfully"}


@router.get("/{instructor_id}", response_model=InstructorProfileResponse)
async def get_instructor_profile(instructor_id: int, db: Session = Depends(get_db)):
    profile = (
        db.query(InstructorProfile)
        .options(joinedload(InstructorProfile.user))
        .options(joinedload(InstructorProfile.services))
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )

    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor profile not found")

    return profile
