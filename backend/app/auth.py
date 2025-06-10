import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .core.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

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
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    # Fix: Use get_secret_value() to get the actual string from SecretStr
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.secret_key.get_secret_value(),  # Changed this line
        algorithm=settings.algorithm
    )
    
    logger.info(f"Created access token for user: {data.get('sub')}")
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependency to get the current authenticated user email from JWT token.
    
    Args:
        token: JWT token from the Authorization header
        
    Returns:
        str: The user's email address
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Fix: Use get_secret_value() here too
        payload = jwt.decode(
            token, 
            settings.secret_key.get_secret_value(),  # Changed this line
            algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            logger.warning("Token payload missing 'sub' field")
            raise credentials_exception
            
        logger.debug(f"Successfully validated token for user: {email}")
        return email
        
    except JWTError as e:
        logger.error(f"JWT validation error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error in token validation: {str(e)}")
        raise credentials_exception