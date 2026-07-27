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
    gemini_api_key: Optional[str] = None

    azure_speech_key: Optional[str] = None
    azure_speech_region: str = "eastus"

    resend_api_key: Optional[str] = None

    jwt_secret: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    superadmin_emails: Optional[str] = None
    admin_emails: Optional[str] = None
    editor_emails: Optional[str] = None

    allowed_email_domains: str = "alieninc.tech"

    ono_function_shared_secret: Optional[str] = None
    ono_function_exec_mode: str = "subprocess"
    ono_function_executable: str = "opencode"
    ono_function_model: Optional[str] = None
    ono_function_timeout: int = 120
    ono_function_rate_limit: int = 20
    ono_function_audit_dir: str = "audit-logs"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
