from azure.identity import ClientSecretCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers.models import (
    ContainerApp, ManagedEnvironment, ManagedServiceIdentity, Template, Container, Configuration, 
    Ingress, ContainerResources, Secret, RegistryCredentials,
    Scale, WorkloadProfile
)
from azure.core.exceptions import AzureError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from core.settings import settings

class AzureContainerAppManager:
    def __init__(self):
        self.subscription_id = settings.azure_subscription_id
        self.resource_group = settings.azure_resource_group
        self.location = settings.azure_location
        
        self.credential = ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret
        )
        
        self.client = ContainerAppsAPIClient(self.credential, self.subscription_id)

    def get_environment_id(self, env_name: str):
        """Lấy hoặc tạo Managed Environment hỗ trợ cả Serverless CPU và Serverless GPU"""
        try:
            logger.info(f"Đang kiểm tra Environment: {env_name}...")
            
            env_payload = ManagedEnvironment(
                location=self.location,
                workload_profiles=[
                    # 1. Serverless CPU Profile
                    WorkloadProfile(
                        workload_profile_type="Consumption",
                        name="Serverless-CPU"
                    ),
                    # 2. Serverless GPU Profile (NVIDIA T4)
                    WorkloadProfile(
                        workload_profile_type="Consumption-GPU-NC8as-T4",
                        name="Serverless-GPU-T4"
                    )
                ]
            )

            poller = self.client.managed_environments.begin_create_or_update(
                self.resource_group,
                env_name,
                env_payload
            )
            env = poller.result()
            logger.info(f"Environment sẵn sàng: {env.id}")
            return env.id
        except Exception as e:
            logger.error(f"Lỗi Environment: {e}")
            raise

    def create_or_update_app(
        self, 
        env_name: str, 
        image: str, 
        cpu: float = None, 
        memory: str = None, 
        port: int = 8000,
        use_gpu: bool = False
    ):
        """Deploy Container App lên Azure với tùy chọn Serverless CPU hoặc Serverless GPU"""
        env_id = self.get_environment_id(env_name)
        registry_secret_name = "registry-password"

        # Tự động chọn Workload Profile và thông số RAM/CPU phù hợp
        if use_gpu or settings.use_gpu:
            workload_profile_name = "Serverless-GPU-T4"
            cpu = cpu if cpu is not None else 4.0
            memory = memory if memory is not None else "16.0Gi"
            logger.info("⚡ Đang triển khai với cấu hình SERVERLESS GPU (NVIDIA T4)...")
        else:
            workload_profile_name = "Serverless-CPU"
            cpu = cpu if cpu is not None else 1.0
            memory = memory if memory is not None else "2.0Gi"
            logger.info("🌱 Đang triển khai với cấu hình SERVERLESS CPU...")

        container_app_config = ContainerApp(
            location=self.location,
            managed_environment_id=env_id,
            workload_profile_name=workload_profile_name,
            identity=ManagedServiceIdentity(type="SystemAssigned"), 
            configuration=Configuration(
                secrets=[Secret(name=registry_secret_name, value=settings.registry_password)],
                registries=[
                    RegistryCredentials(
                        server=settings.registry_server,
                        username=settings.registry_username,
                        password_secret_ref=registry_secret_name
                    )
                ],
                ingress=Ingress(
                    external=True, 
                    target_port=port,
                    transport="http",
                    allow_insecure=True
                )
            ),
            template=Template(
                containers=[
                    Container(
                        name="ai-container",
                        image=image,
                        resources=ContainerResources(cpu=cpu, memory=memory)
                    )
                ],
                scale=Scale(
                    min_replicas=0,
                    max_replicas=2,
                )
            )
        )

        try:
            logger.info(f"Đang triển khai Container App [{settings.app_name}]...")
            poller = self.client.container_apps.begin_create_or_update(
                self.resource_group,
                settings.app_name,
                container_app_config
            )
            result = poller.result()
            fqdn = result.configuration.ingress.fqdn if result.configuration and result.configuration.ingress else "No Ingress"
            logger.info(f"Khởi tạo thành công! FQDN: {fqdn}")
            return {
                "name": result.name,
                "fqdn": fqdn,
                "provisioning_state": result.provisioning_state
            }
        except AzureError as e:
            logger.error(f"Lỗi Azure khi deploy: {e}")
            return None

    def stop_app_completely(self) -> bool:
        """Dừng Container App bằng cách deactivate tất cả các active revision."""
        try:
            logger.info(f"Bắt đầu dừng Container App: {settings.app_name} trong RG: {self.resource_group}")

            revisions = self.client.container_apps_revisions.list_revisions(
                resource_group_name=self.resource_group,
                container_app_name=settings.app_name
            )

            deactivated_count = 0

            for rev in revisions:
                if rev.active:
                    logger.info(f"Đang deactivate revision: {rev.name}...")
                    self.client.container_apps_revisions.deactivate_revision(
                        resource_group_name=self.resource_group,
                        container_app_name=settings.app_name,
                        revision_name=rev.name
                    )
                    deactivated_count += 1

            if deactivated_count == 0:
                logger.info(f"Container App '{settings.app_name}' hiện đã tắt từ trước.")
            else:
                logger.info(f"Đã dừng thành công Container App '{settings.app_name}'.")

            return True

        except Exception as e:
            logger.error(f"Lỗi khi dừng App: {e}")
            return False

    def start_app(self) -> bool:
        """Bật lại Container App bằng cách activate revision mới nhất."""
        try:
            logger.info(f"Bắt đầu bật lại Container App: {settings.app_name}")

            app = self.client.container_apps.get(self.resource_group, settings.app_name)
            latest_revision_name = app.latest_revision_name

            if not latest_revision_name:
                logger.warning(f"Không tìm thấy revision nào cho App: {settings.app_name}")
                return False

            logger.info(f"Đang activate revision mới nhất: {latest_revision_name}...")

            self.client.container_apps_revisions.activate_revision(
                resource_group_name=self.resource_group,
                container_app_name=settings.app_name,
                revision_name=latest_revision_name
            )

            logger.info(f"Đã bật lại Container App '{settings.app_name}' thành công.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi bật lại App: {str(e)}")
            return False

    def get_app_status(self):
        """Lấy trạng thái hiện tại của App"""
        try:
            app = self.client.container_apps.get(self.resource_group, settings.app_name)
            return {
                "name": app.name,
                "running_status": app.provisioning_state,
                "latest_revision": app.latest_revision_name
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin app: {e}")
            return None
