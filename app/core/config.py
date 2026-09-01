from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings

# Configuration model that loads required database/auth settings and provides defaults for JWT behavior.
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # SMTP settings for security-alert emails. All optional — if SMTP_HOST is
    # unset, alert emails are skipped (and logged) instead of failing, so
    # the app still runs fine in dev/test without any mail server configured.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    # Address alert emails are sent "from". Defaults to SMTP_USERNAME if unset.
    SMTP_FROM_EMAIL: Optional[str] = None
    # Address(es) that receive security-alert emails, comma-separated for multiple.
    ALERT_ADMIN_EMAIL: Optional[str] = None
    # Pool for each of the 12 workers initialized in Dokcerfile
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    # Redis URL for Celery broker and result backend. Defaults to a local Redis instance if unset.
    REDIS_URL: str = "redis://localhost:6379/0"

    # Tell Pydantic Settings to load environment variables from the .env file.
    class Config:
        env_file = ".env"

# Cache the Settings instance so the application reuses one configuration object instead of rebuilding it repeatedly.
@lru_cache
def get_settings() -> Settings:
    return Settings()