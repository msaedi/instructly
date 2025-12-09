import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, Optional, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidIssuerError, PyJWTError
from passlib.context import CryptContext

from .core.config import settings
from .database import SessionLocal
from .models.user import User
from .repositories.beta_repository import BetaAccessRepository
from .utils.cookies import session_cookie_candidates

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed bcrypt hash for timing attack prevention.
# Used when user doesn't exist to prevent timing-based user enumeration.
# This is a valid bcrypt hash of "timing_attack_prevention_dummy_password"
DUMMY_HASH_FOR_TIMING_ATTACK = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.V4ferVKnNaOuJi"

# Dedicated thread pool for CPU-bound password operations
# 4 workers allows 4 concurrent bcrypt operations without blocking event loop
_password_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bcrypt_")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def _secret_value(secret_obj: Any) -> str:
    getter = getattr(secret_obj, "get_secret_value", None)
    if callable(getter):
        return cast(str, getter())
    return cast(str, secret_obj)


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
        return bool(pwd_context.verify(plain_password, hashed_password))
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
    hashed = pwd_context.hash(password)
    return str(hashed)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """
    Non-blocking password verification using thread pool.

    Runs bcrypt in a separate thread so the event loop remains responsive
    for other async operations (DB queries, SSE, etc.) during password hashing.

    Args:
        plain_password: The plain text password
        hashed_password: The hashed password to compare against

    Returns:
        bool: True if password matches, False otherwise
    """
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _password_executor,
            pwd_context.verify,
            plain_password,
            hashed_password,
        )
        return bool(result)
    except Exception as e:
        logger.error(f"Error verifying password async: {str(e)}")
        return False


async def get_password_hash_async(password: str) -> str:
    """
    Non-blocking password hashing using thread pool.

    Args:
        password: The plain text password to hash

    Returns:
        str: The hashed password
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _password_executor,
        pwd_context.hash,
        password,
    )
    return str(result)


def _token_claim_requirements() -> tuple[bool, Optional[str], Optional[str]]:
    """Return whether to enforce audience/issuer along with expected values."""

    try:
        site_mode = os.getenv("SITE_MODE", "").lower().strip()
    except Exception:
        site_mode = ""
    enforce_aud = site_mode in {"preview", "prod", "production", "live", "beta"} and not bool(
        getattr(settings, "is_testing", False)
    )
    if not enforce_aud:
        return False, None, None
    expected_aud = "preview" if site_mode == "preview" else "prod"
    if site_mode == "preview":
        expected_iss = f"https://{settings.preview_api_domain}"
    else:
        expected_iss = f"https://{settings.prod_api_domain}"
    return True, expected_aud, expected_iss


def decode_access_token(token: str, *, enforce_audience: bool | None = None) -> Dict[str, Any]:
    """Decode a JWT access token enforcing preview/prod issuer/audience when required."""

    enforce_default, expected_aud, expected_iss = _token_claim_requirements()
    if enforce_audience is not None:
        enforce = enforce_audience
    else:
        enforce = enforce_default

    secret = _secret_value(settings.secret_key)
    if enforce and expected_aud:
        payload_raw = jwt.decode(
            token,
            secret,
            algorithms=[settings.algorithm],
            audience=expected_aud,
        )
        payload = cast(Dict[str, Any], payload_raw)
        if expected_iss and payload.get("iss") != expected_iss:
            raise InvalidIssuerError("Unexpected token issuer")
        return payload
    payload_raw = jwt.decode(
        token,
        secret,
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    return cast(Dict[str, Any], payload_raw)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
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
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

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
    encoded_jwt = cast(
        str,
        jwt.encode(
            to_encode,
            _secret_value(settings.secret_key),
            algorithm=settings.algorithm,
        ),
    )

    logger.info(f"Created access token for user: {data.get('sub')}")
    return encoded_jwt


def create_temp_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived temp token for 2FA challenges."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(seconds=60))
    to_encode.update(
        {
            "exp": expire,
            "iss": settings.temp_token_iss,
            "aud": settings.temp_token_aud,
        }
    )
    secret_source = settings.temp_token_secret or settings.secret_key
    encoded_jwt = cast(
        str,
        jwt.encode(
            to_encode,
            _secret_value(secret_source),
            algorithm=settings.algorithm,
        ),
    )
    return encoded_jwt


async def get_current_user(
    request: Request, token: Optional[str] = Depends(oauth2_scheme_optional)
) -> str:
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

            if hasattr(request, "cookies"):
                # TODO: remove legacy cookie fallback once __Host- migration is complete.
                for cookie_name in session_cookie_candidates(site_mode):
                    cookie_token = request.cookies.get(cookie_name)
                    if cookie_token:
                        token = cookie_token
                        logger.debug(f"Using {cookie_name} cookie for authentication")
                        break

        if not token:
            raise not_authenticated
        payload = decode_access_token(token)
        email_obj = payload.get("sub")
        if not isinstance(email_obj, str):
            email: str | None = None
        else:
            email = email_obj
        if email is None:
            logger.warning("Token payload missing 'sub' field")
            credentials_exception = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
            raise credentials_exception

        logger.debug(f"Successfully validated token for user: {email}")
        return email

    except HTTPException as http_exc:
        # Preserve explicit HTTPExceptions (e.g., Not authenticated)
        raise http_exc
    except PyJWTError as e:
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

        if hasattr(request, "cookies"):
            # TODO: remove legacy cookie fallback once __Host- migration is complete.
            for cookie_name in session_cookie_candidates(site_mode):
                cookie_token = request.cookies.get(cookie_name)
                if cookie_token:
                    token = cookie_token
                    break
        if not token:
            return None

    try:
        payload = decode_access_token(token)
        email_obj = payload.get("sub")
        email: str | None = email_obj if isinstance(email_obj, str) else None
        if email is None:
            logger.warning("Token payload missing 'sub' field")
            return None

        logger.debug(f"Successfully validated optional token for user: {email}")
        return email

    except PyJWTError as e:
        logger.debug(f"JWT validation error in optional auth: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in optional token validation: {str(e)}")
        return None
