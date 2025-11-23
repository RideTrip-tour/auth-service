from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jwt_secret: str = "secret"
    jwt_algorithm: str = "HS256"
    redis_url: str = "redis://127.0.0.1:6379"
    redis_ttl: int = 300  # время жизни кеша по умолчанию
    db_name: str = "rtt"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = "platform"
    db_pass: str = "12345"
    db_driver: str = "postgresql+asyncpg"
    access_token_expire_sec: int = 60 * 60 * 24 * 7
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True
    )


settings = Settings()
