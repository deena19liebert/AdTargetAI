# app/core/config.py
from typing import Optional, List
from pydantic import validator, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
import logging

load_dotenv()

# define logger BEFORE using it
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    ENVIRONMENT: str = "development"
    
    # Mistral AI
    MISTRAL_API_KEY: str = Field(..., env="MISTRAL_API_KEY")
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"

    # Facebook
    FACEBOOK_ACCESS_TOKEN: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    FACEBOOK_APP_ID: Optional[str] = None
    FACEBOOK_AD_ACCOUNT_ID: Optional[str] = None
    
    JWT_SECRET_KEY: str = Field(default="change-me", env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 
    
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = None 
    
    CREDITS_PER_CAMPAIGN_GENERATION: float = 10.0  # Cost to generate a campaign
    CREDITS_PER_EXPORT_DRY_RUN: float = 0.0  # Dry-run is free
    CREDITS_PER_EXPORT_REAL_FACEBOOK: float = 5.0  # Additional cost for real FB export
    CREDITS_PER_EXPORT_REAL_GOOGLE: float = 5.0  # Additional cost for real Google export
    
    # Pricing: How many credits per INR?
    CREDITS_PER_INR: float = 1.0  # 1 INR = 1 credit (adjust as needed)

    # Credit packages (INR : Credits)
    CREDIT_PACKAGES: dict = {
        "starter": {"amount_inr": 100, "credits": 100, "bonus": 0},
        "basic": {"amount_inr": 500, "credits": 550, "bonus": 50},  # 10% bonus
        "pro": {"amount_inr": 1000, "credits": 1200, "bonus": 200},  # 20% bonus
        "enterprise": {"amount_inr": 5000, "credits": 6500, "bonus": 1500}  # 30% bonus
    }
    
    # Free credits for new users
    FREE_CREDITS_ON_SIGNUP: float = 20.0  # Give new users 20 free credits
    
    # Minimum credit balance warnings
    LOW_CREDIT_THRESHOLD: float = 5.0 
    
    # Admin / safety
    ADMIN_KEY: Optional[str] = None
    ADMIN_KEY_HASH: Optional[str] = None
    ALLOW_REAL_ADS: bool = False

    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")

    # Observability
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"


    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        if not v or v == "":
            raise ValueError("DATABASE_URL must be set")
        if "postgresql" not in v:
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v

    @validator("FACEBOOK_ACCESS_TOKEN")
    def validate_facebook_token(cls, v):
        if v and len(v) < 50:
            raise ValueError("FACEBOOK_ACCESS_TOKEN seems invalid (too short)")
        return v
    
    # Application
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

try:
    settings = Settings()
    logger.info("✅ Configuration validated successfully")
except Exception as e:
    logger.error(f"❌ Configuration validation failed: {e}")
    raise
