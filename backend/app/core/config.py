from pydantic_settings import BaseSettings
from pydantic import SecretStr
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent.parent / '.env'  # Goes up to backend/.env
load_dotenv(env_path)

class Settings(BaseSettings):
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str

    class Config:
        env_file = str(env_path)  # Use the correct path
        case_sensitive = True
        extra = "ignore"

settings = Settings()