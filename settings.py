from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Azure Config
    azure_subscription_id: str
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    
    azure_resource_group: str = "AI-Hub-RG"
    azure_location: str = "eastus"
    azure_container_env: str = "ai-hub-env"

    # AI Vendor Keys
    openai_api_key: Optional[str] = None
    
    # Tự động đọc file .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Khởi tạo object settings để dùng chung toàn hệ thống
settings = Settings()