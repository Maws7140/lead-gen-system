"""
Application configuration and settings
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "LeadGen Pro"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "your-secret-key-change-in-production"

    # API Keys
    OPENAI_API_KEY: str = ""
    AIRTABLE_API_KEY: str = ""
    AIRTABLE_BASE_ID: str = ""
    AIRTABLE_TABLE_NAME: str = "Leads"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./leadgen.db"

    # Scraping settings
    SCRAPE_TIMEOUT: int = 30
    MAX_CONCURRENT_SCRAPES: int = 5
    RATE_LIMIT_DELAY: float = 1.0
    USER_AGENT: str = "LeadGenPro/2.0 (Compatible; Lead Research Bot)"

    # LLM Settings
    LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096

    # Redis (for background tasks)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # Email settings (for campaigns)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # Twilio (for SMS)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience function
settings = get_settings()
