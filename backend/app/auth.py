import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, Optional, cast
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidIssuerError, PyJWTError

from .core.config import settings
from .utils.cookies import session_cookie_candidates

logger = logging.getLogger(__name__)

# Argon2id password hasher with OWASP recommended settings
# https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
# Benefits over bcrypt: memory-hard (resists GPU attacks), 2-4x faster verification
_password_hasher = PasswordHasher(
    time_cost=2,  # Number of iterations
    memory_cost=19456,  # 19 MB (in KB) - memory-hard for GPU resistance
    parallelism=1,  # Number of parallel threads
    hash_len=32,  # Length of the hash in bytes
    salt_len=16,  # Length of random salt
)

# Pre-computed Argon2id hash for timing attack prevention.
# Used when user doesn't exist to prevent timing-based user enumeration.
# This is a valid Argon2id hash of "timing_attack_prevention_dummy_password"
DUMMY_HASH_FOR_TIMING_ATTACK = "$argon2id$v=19$m=19456,t=2,p=1$2nLJrVFbOidsu8s0BtjUog$UaJlDNrniWtZRjiLNlROqWazzB0qTUxIosxsJYQaHKs"

# Dedicated thread pool for CPU-bound password operations
# With Argon2id, more threads help parallelize the memory-hard operations.
# 8 workers × 2 uvicorn workers = 16 concurrent password ops (health checks stay responsive)
_password_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="argon2_")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def _secret_value(secret_obj: Any) -> str:
    getter = getattr(secret_obj, "get_secret_value", None)
    if callable(getter):
        return cast(str, getter())
    return cast(str, secret_obj)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password using Argon2id.

    Args:
        plain_password: The plain text password
        hashed_password: The hashed password to compare against

    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        _password_hasher.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False
    except InvalidHashError as e:
        logger.error(f"Invalid hash format: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using Argon2id with OWASP recommended settings.

    Args:
        password: The plain text password to hash

    Returns:
        str: The hashed password
    """
    return cast(str, _password_hasher.hash(password))


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """
    Non-blocking password verification using thread pool.

    Runs Argon2id verification in a separate thread so the event loop remains
    responsive for other async operations (DB queries, SSE, etc.).

    Args:
        plain_password: The plain text password
        hashed_password: The hashed password to compare against

    Returns:
        bool: True if password matches, False otherwise
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _password_executor,
            verify_password,
            plain_password,
            hashed_password,
        )
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
    return await loop.run_in_executor(
        _password_executor,
        get_password_hash,
        password,
    )


def password_needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be updated (e.g., after config change).

    This can be used during login to transparently upgrade hashes when
    the Argon2id parameters are changed.

    Args:
        hashed_password: The current hash to check

    Returns:
        bool: True if the hash should be regenerated with current settings
    """
    try:
        return cast(bool, _password_hasher.check_needs_rehash(hashed_password))
    except Exception:
        return False


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


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    beta_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data: The data to encode in the token
        expires_delta: Optional expiration time delta
        beta_claims: Optional pre-fetched beta claims to include in token.
                     Pass this from fetch_user_for_auth() to avoid blocking DB lookup.

    Returns:
        str: The encoded JWT token
    """
    to_encode = data.copy()
    now_utc = datetime.now(timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode.update(
        {
            "exp": expire,
            "iat": int(now_utc.timestamp()),
            "jti": str(uuid.uuid4()),
        }
    )

    # Include pre-fetched beta claims if provided (no DB lookup needed)
    if beta_claims:
        to_encode.update(beta_claims)

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
    Dependency to get the current authenticated user identifier from JWT token.

    Args:
        token: JWT token from the Authorization header

    Returns:
        str: The user's identifier (ULID)

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
                # Legacy cookie fallback for __Host- migration compatibility.
                for cookie_name in session_cookie_candidates(site_mode):
                    cookie_token = request.cookies.get(cookie_name)
                    if cookie_token:
                        token = cookie_token
                        logger.debug(f"Using {cookie_name} cookie for authentication")
                        break

        if not token:
            raise not_authenticated
        payload = decode_access_token(token)
        if not payload.get("jti"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token format outdated, please re-login",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id_obj = payload.get("sub")
        if not isinstance(user_id_obj, str):
            user_id: str | None = None
        else:
            user_id = user_id_obj
        if user_id is None:
            logger.warning("Token payload missing 'sub' field")
            credentials_exception = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
            raise credentials_exception

        logger.debug(f"Successfully validated token for user: {user_id}")
        return user_id

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
    Dependency to get the current authenticated user identifier from JWT token if present.

    This function returns None if no token is provided or if the token is invalid,
    instead of raising an exception. Used for endpoints that support both
    authenticated and anonymous access.

    Args:
        token: Optional JWT token from the Authorization header

    Returns:
        str: The user's identifier (ULID) if authenticated, None otherwise
    """
    if not token:
        # Mirror cookie fallback behavior from get_current_user so optional
        # auth works with cookie-only sessions in preview/prod/local.
        try:
            site_mode = os.getenv("SITE_MODE", "").lower().strip()
        except Exception:
            site_mode = ""

        if hasattr(request, "cookies"):
            # Legacy cookie fallback for __Host- migration compatibility.
            for cookie_name in session_cookie_candidates(site_mode):
                cookie_token = request.cookies.get(cookie_name)
                if cookie_token:
                    token = cookie_token
                    break
        if not token:
            return None

    try:
        payload = decode_access_token(token)
        if not payload.get("jti"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token format outdated, please re-login",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id_obj = payload.get("sub")
        user_id: str | None = user_id_obj if isinstance(user_id_obj, str) else None
        if user_id is None:
            logger.warning("Token payload missing 'sub' field")
            return None

        logger.debug(f"Successfully validated optional token for user: {user_id}")
        return user_id

    except HTTPException:
        raise
    except PyJWTError as e:
        logger.debug(f"JWT validation error in optional auth: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in optional token validation: {str(e)}")
        return None
