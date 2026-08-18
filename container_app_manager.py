from azure.identity import DefaultAzureCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers.models import (
    ContainerApp, Template, Container, Configuration, 
    Ingress, ResourceResources, Scale, ManagedEnvironment
)
from azure.core.exceptions import AzureError
import logging

# Thiết lập logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AzureContainerAppManager:
    def __init__(self, subscription_id: str, resource_group: str, location: str):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.credential = DefaultAzureCredential()
        self.client = ContainerAppsAPIClient(self.credential, self.subscription_id)

    def get_environment_id(self, env_name: str):
        """Lấy hoặc tạo Managed Environment ID"""
        try:
            poller = self.client.managed_environments.begin_create_or_update(
                self.resource_group,
                env_name,
                ManagedEnvironment(location=self.location)
            )
            env = poller.result()
            return env.id
        except Exception as e:
            logger.error(f"Lỗi khi lấy Environment: {e}")
            raise

    def create_or_update_app(self, app_name: str, env_name: str, image: str, cpu: float = 0.5, memory: str = "1.0Gi", port: int = 80):
        """Tạo mới hoặc cập nhật một Container App"""
        env_id = self.get_environment_id(env_name)
        
        container_app_config = ContainerApp(
            location=self.location,
            managed_environment_id=env_id,
            configuration=Configuration(
                ingress=Ingress(
                    external=True,
                    target_port=port,
                    allow_insecure=False,
                    transport="auto"
                )
            ),
            template=Template(
                containers=[
                    Container(
                        name=f"{app_name}-container",
                        image=image,
                        resources=ResourceResources(cpu=cpu, memory=memory)
                    )
                ],
                scale=Scale(min_replicas=0, max_replicas=3) # Scale về 0 để tiết kiệm tiền khi không dùng
            )
        )

        try:
            logger.info(f"Đang triển khai Container App: {app_name}...")
            poller = self.client.container_apps.begin_create_or_update(
                self.resource_group,
                app_name,
                container_app_config
            )
            result = poller.result()
            logger.info(f"Triển khai thành công: {result.configuration.ingress.fqdn}")
            return {
                "name": result.name,
                "fqdn": result.configuration.ingress.fqdn,
                "provisioning_state": result.provisioning_state
            }
        except AzureError as e:
            logger.error(f"Lỗi Azure: {e}")
            return None

    def list_apps(self):
        """Liệt kê tất cả các Container Apps trong Resource Group"""
        apps = self.client.container_apps.list_by_resource_group(self.resource_group)
        return [{"name": app.name, "fqdn": app.configuration.ingress.fqdn} for app in apps]

    def delete_app(self, app_name: str):
        """Xóa một Container App"""
        try:
            logger.info(f"Đang xóa App: {app_name}...")
            poller = self.client.container_apps.begin_delete(self.resource_group, app_name)
            poller.result()
            logger.info(f"Đã xóa thành công {app_name}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi xóa: {e}")
            return False

    def stop_app(self, app_name: str):
        """Dừng App bằng cách set scale replicas về 0 (Tiết kiệm chi phí)"""
        # Lưu ý: Container App không có nút 'Stop' như VM, ta điều chỉnh Scale.
        app = self.client.container_apps.get(self.resource_group, app_name)
        app.template.scale.min_replicas = 0
        app.template.scale.max_replicas = 0
        
        poller = self.client.container_apps.begin_create_or_update(
            self.resource_group, app_name, app
        )
        return poller.result().provisioning_state