import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import database, models
from ..auth import create_access_token, get_current_user, get_password_hash, verify_password
from ..core.config import settings
from ..core.constants import ERROR_USER_NOT_FOUND
from ..schemas import Token, UserCreate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(database.get_db)):
    """
    Register a new user.

    Args:
        user: User creation data
        db: Database session

    Returns:
        UserResponse: The created user

    Raises:
        HTTPException: If email already registered
    """
    logger.info(f"Registration attempt for email: {user.email}")

    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        logger.warning(f"Registration failed - email already exists: {user.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        role=user.role,
    )

    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        logger.info(f"Successfully registered user: {user.email} with role: {user.role}")
        return db_user
    except Exception as e:
        logger.error(f"Error registering user {user.email}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user",
        )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
):
    """
    Login with username (email) and password.

    Args:
        form_data: OAuth2 form with username and password
        db: Database session

    Returns:
        Token: Access token and token type

    Raises:
        HTTPException: If credentials are invalid
    """
    logger.info(f"Login attempt for user: {form_data.username}")

    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)

    logger.info(f"Successful login for user: {user.email}")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Get current user information.

    Args:
        current_user: Current user email from JWT
        db: Database session

    Returns:
        UserResponse: Current user data

    Raises:
        HTTPException: If user not found
    """
    user = db.query(models.User).filter(models.User.email == current_user).first()
    if not user:
        logger.error(f"User not found in database: {current_user}")
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    return user
