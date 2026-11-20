from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareBridge AI API"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str | None = None
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str | None = None
    data_dir: str = ".carebridge-mvp"
    max_upload_bytes: int = 10_485_760

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

@lru_cache
def get_settings() -> Settings:
    return Settings()
