import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jwt_secret: str = os.getenv("JWT_SECRET", "secret")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    gateway_name: str = os.getenv("GATEWAY_NAME", "Gate")

    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379")
    redis_ttl: int = 300  # время жизни кеша по умолчанию

    # Database
    db_host: str = os.getenv("DB_HOST", "postgres")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "mydb"))
    db_user: str = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "user"))
    db_pass: str = os.getenv("DB_PASS", os.getenv("POSTGRES_PASSWORD", "password123"))
    db_driver: str = "postgresql+asyncpg"

    # Email
    mail_server: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    mail_port: int = int(os.getenv("MAIL_PORT", "587"))
    mail_username: str = os.getenv("MAIL_USERNAME", "")
    mail_password: str = os.getenv("MAIL_PASSWORD", "")
    mail_from: str = os.getenv("MAIL_FROM", "")
    mail_from_name: str = os.getenv("MAIL_FROM_NAME", "Trip Constructor")
    mail_starttls: bool = os.getenv("MAIL_STARTTLS", "true").lower() == "true"
    mail_ssl_tls: bool = os.getenv("MAIL_SSL_TLS", "false").lower() == "true"

    # Register
    access_token_expire_sec: int = 60 * 60 * 24 * 7
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    origin: str = os.getenv("ORIGIN", "http://trip.com")
    lk_path: str = os.getenv("LK_PATH", "/users/me/")

    model_config = SettingsConfigDict(
        extra="ignore",
    )


settings = Settings()
