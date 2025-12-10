# app/core/config.py
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    # Mistral AI
    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"

    # Facebook
    FACEBOOK_ACCESS_TOKEN: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    FACEBOOK_APP_ID: Optional[str] = None
    FACEBOOK_AD_ACCOUNT_ID: Optional[str] = None

    # Admin / safety
    ADMIN_KEY: Optional[str] = None
    ADMIN_KEY_HASH: Optional[str] = None 
    ALLOW_REAL_ADS: bool = False

    # Application
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

settings = Settings()
