from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    DATABASE_URL: str
    ENCRYPTION_KEY: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    META_APP_ID: str
    META_CLIENT_SECRET: str
    META_WEBHOOK_VERIFY_TOKEN: str 
    META_APP_VERSION: str = "v18.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DATABASE_URL", "ENCRYPTION_KEY", "SECRET_KEY", "META_APP_ID", "META_CLIENT_SECRET", "META_WEBHOOK_VERIFY_TOKEN")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v

# ADD THIS LINE TO CREATE THE INSTANCE:
settings = Settings()