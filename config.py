from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jwt_secret: str
    jwt_algorithm: str
    redis_url: str = "redis://127.0.0.1:6379"
    redis_ttl: int = 300  # время жизни кеша по умолчанию
    db_url: str
    access_token_expire_min: int = 60

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True
    )


settings = Settings()
