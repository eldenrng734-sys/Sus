from pathlib import Path

from pydantic import SecretStr
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

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cookie_secure: bool = False
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # -------------------------------------------------------------------------
    # Meta / WhatsApp platform-level secrets (never per-tenant, never in DB)
    # WhatsApp and Messenger/Lead Ads share the same Meta app secret.
    # -------------------------------------------------------------------------
    # HMAC key for all Meta webhook signatures (X-Hub-Signature-256).
    meta_app_secret: SecretStr = SecretStr("")
    # Token compared against hub.verify_token in GET handshake challenges.
    webhook_verify_token: SecretStr = SecretStr("")
    # Graph API version — set in env, never hardcoded in business logic.
    meta_graph_version: str = "v21.0"

    # AES-256-GCM key for encrypting per-tenant credentials in the DB.
    # Must be a base64-encoded 32-byte value.  Generate with:
    #   python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
    integration_encryption_key: SecretStr = SecretStr("")

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
