# backend/app/core/config.py
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ConfigDict, SecretStr
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Load .env file only if not in CI
if not os.getenv("CI"):
    env_path = Path(__file__).parent.parent.parent / ".env"  # Goes up to backend/.env
    logger.info(f"[CONFIG] Looking for .env at: {env_path}")
    logger.info(f"[CONFIG] .env exists: {env_path.exists()}")
    logger.info(f"[CONFIG] Absolute path: {env_path.absolute()}")
    load_dotenv(env_path)


class Settings(BaseSettings):
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str

    # Email settings
    resend_api_key: str = ""
    from_email: str = "noreply@instainstru.com"

    # Frontend URL - will use production URL if not set
    frontend_url: str = "https://instructly-ten.vercel.app"

    # Environment
    environment: str = "production"  # or "development"

    # Cache settings
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 3600  # 1 hour in seconds

    # Use ConfigDict instead of Config class (Pydantic V2 style)
    model_config = ConfigDict(
        env_file=".env" if not os.getenv("CI") else None,
        case_sensitive=False,  # Changed to False - allows SECRET_KEY to match secret_key
        extra="ignore",
    )


settings = Settings()
