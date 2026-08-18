from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Azure Config
    app_name: str
    azure_subscription_id: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    
    azure_resource_group: str = "AI-Hub-RG"
    azure_location: str = "eastus"
    azure_container_env: str = "ai-hub-env"

    # AI Vendor Keys (Optional)
    openai_api_key: Optional[str] = None

    # Registry
    registry_server: str
    registry_username: str
    registry_password: str

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding='utf-8',
        extra="ignore"
    )

settings = Settings()