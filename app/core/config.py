from functools import lru_cache
from pydantic_settings import BaseSettings

# Configuration model that loads required database/auth settings and provides defaults for JWT behavior.
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Tell Pydantic Settings to load environment variables from the .env file.
    class Config:
        env_file = ".env"

# Cache the Settings instance so the application reuses one configuration object instead of rebuilding it repeatedly.
@lru_cache
def get_settings() -> Settings:
    return Settings()