from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "auth-service"
    # =========================
    # Security
    # =========================
    jwt_secret: str = "secretsecretsecretsecretsecretsecret"
    jwt_algorithm: str = "HS256"
    gateway_name: str = "Gate"
    debug: bool = True

    # =========================
    # Redis
    # =========================
    redis_url: str = "redis://redis:6379"
    redis_ttl: int = 300

    # =========================
    # Database
    # =========================
    db_host: str = Field(validation_alias='DB_AUTH_SERVICE_HOST', default="127.0.0.1")
    db_port: int = Field(validation_alias='DB_AUTH_SERVICE_PORT', default=5432)
    db_name: str = Field(validation_alias='DB_AUTH_SERVICE_NAME', default="rrt")
    db_user: str = Field(validation_alias='DB_AUTH_SERVICE_USER', default="platform")
    db_pass: str = Field(validation_alias='DB_AUTH_SERVICE_PASS', default="12345")
    db_driver: str = "postgresql+asyncpg"

    # =========================
    # Email
    # =========================
    mail_server: str = "smtp.gmail.com"
    mail_port: int = 587
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_from_name: str = "Trip Constructor"
    mail_starttls: bool = True
    mail_ssl_tls: bool = False
    support_email: str = Field(
        validation_alias='SUPPORT_EMAIL',
        default="support@3shagado.ru",
    )

    # =========================
    # Auth
    # =========================
    access_token_expire_sec: int = 60 * 15
    refresh_token_expire_sec: int = 60 * 60 * 24 * 7
    reset_password_token_lifetime_seconds: int = Field(
        validation_alias='RESET_PASSWORD_TOKEN_LIFETIME_SECONDS',
        default=60 * 60 * 2,
    )
    verification_token_lifetime_seconds: int = Field(
        validation_alias='VERIFICATION_TOKEN_LIFETIME_SECONDS',
        default=60 * 60,
    )
    change_email_token_lifetime_seconds: int = Field(
        validation_alias='CHANGE_EMAIL_TOKEN_LIFETIME_SECONDS',
        default=60 * 60,
    )
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    origin: str = "http://trip.com"
    lk_path: str = "/users/me/"
    password_recovery_path: str = Field(
        validation_alias='PASSWORD_RECOVERY_PATH',
        default="/reset-password",
    )

    refresh_token_path: str = "/api/auth/refresh"
    refresh_token_name: str = "refresh_token"

    # =========================
    # Config
    # =========================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        secrets_dir='/run/secrets'
    )


settings = Settings()
