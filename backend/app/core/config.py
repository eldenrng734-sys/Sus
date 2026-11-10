from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    migration_database_url: str = ""
    smtp_host: str = "mailpit"
    password_reset_ttl_minutes: int = 30
    email_verification_ttl_hours: int = 24
    smtp_port: int = 1025
    mail_from: str = "no-reply@crm.local"
    frontend_base_url: str = "http://localhost:3000"
    password_reset_ttl_minutes: int = 30
    email_verification_ttl_hours: int = 24
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    cookie_secure: bool = False  # set COOKIE_SECURE=true in staging/production
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
