from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    # Use consistent uppercase to match .env
    DATABASE_URL: str
    ENCRYPTION_KEY: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Fixed typo from MATA to META
    META_APP_ID: str
    META_CLIENT_SECRET: str
    META_APP_VERSION: str = "v18.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DATABASE_URL", "ENCRYPTION_KEY", "SECRET_KEY", "META_APP_ID", "META_CLIENT_SECRET")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v

settings = Settings()