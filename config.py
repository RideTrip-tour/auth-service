from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =========================
    # Security
    # =========================
    jwt_secret: str = "secret"
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
    db_host: str = Field(validation_alias='DB_AUTH_SERVICE_HOST', default="postgres")
    db_port: int = Field(validation_alias='DB_AUTH_SERVICE_PORT', default=5432)
    db_name: str = Field(validation_alias='DB_AUTH_SERVICE_NAME', default="mydb")
    db_user: str = Field(validation_alias='DB_AUTH_SERVICE_USER', default="user")
    db_pass: str = Field(validation_alias='DB_AUTH_SERVICE_PASS', default="password123")
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

    # =========================
    # Auth
    # =========================
    access_token_expire_sec: int = 60 * 15
    refresh_token_expire_sec: int = 60 * 60 * 24 * 7
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    origin: str = "http://trip.com"
    lk_path: str = "/users/me/"

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
