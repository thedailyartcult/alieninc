from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "Panteon"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = Field(
        default="sqlite+aiosqlite:///panteon.db"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    jwt_secret: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
