import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .core.config import settings
from .database import SessionLocal
from .models.user import User
from .repositories.beta_repository import BetaAccessRepository

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: The plain text password
        hashed_password: The hashed password to compare against

    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: The plain text password to hash

    Returns:
        str: The hashed password
    """
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: The data to encode in the token
        expires_delta: Optional expiration time delta

    Returns:
        str: The encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode.update({"exp": expire})

    # Enrich with beta claims when possible (email -> user -> beta access)
    try:
        email = data.get("sub")
        if email:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.email == email).first()
                if user:
                    beta_repo = BetaAccessRepository(db)
                    beta = beta_repo.get_latest_for_user(user.id)
                    if beta:
                        to_encode.update(
                            {
                                "beta_access": True,
                                "beta_role": beta.role,
                                "beta_phase": beta.phase,
                                "beta_invited_by": beta.invited_by_code,
                            }
                        )
            finally:
                db.close()
    except Exception as e:
        logger.warning(f"Unable to enrich JWT with beta claims: {e}")
    # Add iss/aud per environment
    try:
        site_mode = os.getenv("SITE_MODE", "").lower().strip()
    except Exception:
        site_mode = ""
    if site_mode == "preview":
        to_encode.update({"iss": f"https://{settings.preview_api_domain}", "aud": "preview"})
    elif site_mode in {"prod", "production", "live"}:
        to_encode.update({"iss": f"https://{settings.prod_api_domain}", "aud": "prod"})

    # Fix: Use get_secret_value() to get the actual string from SecretStr
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),  # Changed this line
        algorithm=settings.algorithm,
    )

    logger.info(f"Created access token for user: {data.get('sub')}")
    return encoded_jwt


async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme_optional)) -> str:
    """
    Dependency to get the current authenticated user email from JWT token.

    Args:
        token: JWT token from the Authorization header

    Returns:
        str: The user's email address

    Raises:
        HTTPException: If token is invalid or expired
    """
    not_authenticated = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Cookie fallback when no Authorization header is present
        if not token:
            try:
                site_mode = os.getenv("SITE_MODE", "").lower().strip()
            except Exception:
                site_mode = ""

            # Read environment-specific cookie
            cookie_name = None
            if site_mode == "preview":
                cookie_name = "sid_preview"
            elif site_mode in {"prod", "production", "live"}:
                cookie_name = "sid_prod"
            elif site_mode == "local" or not site_mode:
                cookie_name = "access_token"

            if cookie_name and hasattr(request, "cookies"):
                cookie_token = request.cookies.get(cookie_name)
                if cookie_token:
                    token = cookie_token
                    logger.debug(f"Using {cookie_name} cookie for authentication")

        if not token:
            raise not_authenticated
        # Decode JWT with appropriate audience enforcement
        site_mode = os.getenv("SITE_MODE", "").lower().strip()
        enforce_aud = (site_mode in {"preview", "prod", "production", "live"}) and not bool(
            getattr(settings, "is_testing", False)
        )
        if enforce_aud:
            expected_aud = "preview" if site_mode == "preview" else "prod"
            payload = jwt.decode(
                token,
                settings.secret_key.get_secret_value(),
                algorithms=[settings.algorithm],
                audience=expected_aud,
            )
            iss = payload.get("iss", "")
            if site_mode == "preview":
                if iss != f"https://{settings.preview_api_domain}":
                    raise invalid_credentials
            else:  # prod family
                if iss != f"https://{settings.prod_api_domain}":
                    raise invalid_credentials
        else:
            # Disable audience verification in tests and non-preview/prod modes
            payload = jwt.decode(
                token,
                settings.secret_key.get_secret_value(),
                algorithms=[settings.algorithm],
                options={"verify_aud": False},
            )
        email: str = payload.get("sub")
        if email is None:
            logger.warning("Token payload missing 'sub' field")
            raise credentials_exception

        logger.debug(f"Successfully validated token for user: {email}")
        return email

    except HTTPException as http_exc:
        # Preserve explicit HTTPExceptions (e.g., Not authenticated)
        raise http_exc
    except JWTError as e:
        logger.error(f"JWT validation error: {str(e)}")
        raise invalid_credentials
    except Exception as e:
        logger.error(f"Unexpected error in token validation: {str(e)}")
        raise invalid_credentials


async def get_current_user_optional(
    request: Request, token: Optional[str] = Depends(oauth2_scheme_optional)
) -> Optional[str]:
    """
    Dependency to get the current authenticated user email from JWT token if present.

    This function returns None if no token is provided or if the token is invalid,
    instead of raising an exception. Used for endpoints that support both
    authenticated and anonymous access.

    Args:
        token: Optional JWT token from the Authorization header

    Returns:
        str: The user's email address if authenticated, None otherwise
    """
    if not token:
        # Mirror cookie fallback behavior from get_current_user so optional
        # auth works with cookie-only sessions in preview/prod/local.
        try:
            site_mode = os.getenv("SITE_MODE", "").lower().strip()
        except Exception:
            site_mode = ""

        cookie_name = None
        if site_mode == "preview":
            cookie_name = "sid_preview"
        elif site_mode in {"prod", "production", "live"}:
            cookie_name = "sid_prod"
        elif site_mode == "local" or not site_mode:
            cookie_name = "access_token"

        if cookie_name and hasattr(request, "cookies"):
            cookie_token = request.cookies.get(cookie_name)
            if cookie_token:
                token = cookie_token
        if not token:
            return None

    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
        )
        email: str = payload.get("sub")
        if email is None:
            logger.warning("Token payload missing 'sub' field")
            return None

        logger.debug(f"Successfully validated optional token for user: {email}")
        return email

    except JWTError as e:
        logger.debug(f"JWT validation error in optional auth: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in optional token validation: {str(e)}")
        return None
