from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Azure authentication
    azure_subscription_id: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str

    # Azure resources
    azure_resource_group: str = "AI-Hub-RG"
    azure_location: str = "eastus"
    azure_container_env: str = "ai-hub-env"
    app_name: str = "model-test-api"

    # Image
    container_image: str

    # Container resources
    container_cpu: float = 1.0
    container_memory: str = "2Gi"
    use_gpu: bool = False

    # Private registry
    registry_server: str
    registry_username: str
    registry_password: str

    # Object storage S3-compatible
    object_storage_endpoint: str
    object_storage_access_key: str
    object_storage_secret_key: str
    object_storage_bucket: str = "trained-models"
    object_storage_region: str = "us-east-1"
    object_storage_secure: bool = True

    # Optional
    openai_api_key: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
