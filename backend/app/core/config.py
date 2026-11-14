from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    migration_database_url: str = ""

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    mail_from: str = "no-reply@crm.local"
    frontend_base_url: str = "http://localhost:3000"

    password_reset_ttl_minutes: int = 30
    email_verification_ttl_hours: int = 24

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    mfa_encryption_key: str = ""
    mfa_issuer: str = "AI Sales Assistant CRM"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cookie_secure: bool = False
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # Webhook verification secrets.
    whatsapp_app_secret: str = ""
    meta_app_secret: str = ""
    webhook_verify_token: str = ""
    cookie_secure: bool = False  # set COOKIE_SECURE=true in staging/production
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = "https://api.anthropic.com/v1/messages"
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 2
    llm_input_price_per_mtok: float = 0.0
    llm_output_price_per_mtok: float = 0.0

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore",
    )


settings = Settings()
