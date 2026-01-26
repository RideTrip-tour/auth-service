import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jwt_secret: str = os.getenv("JWT_SECRET", "secret")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    
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
    
    access_token_expire_sec: int = 60 * 60 * 24 * 7
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    model_config = SettingsConfigDict(
        extra="ignore",
    )


settings = Settings()
