from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Object storage S3-compatible
    object_storage_endpoint: str
    object_storage_access_key: str
    object_storage_secret_key: str
    object_storage_bucket: str
    object_storage_region: str
    object_storage_secure: bool = True

    # Training defaults
    default_n_samples: int = 50_000
    default_n_features: int = 20
    default_n_estimators: int = 30
    default_target_ram_mb: int = 128

    model_dir: str = "/tmp/models"

    # Optional
    app_name: str = "model-test-api"
    openai_api_key: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
