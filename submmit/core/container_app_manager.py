import logging

from azure.core.exceptions import AzureError
from azure.identity import ClientSecretCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers.models import (
    Configuration,
    Container,
    ContainerApp,
    ContainerResources,
    EnvironmentVar,
    HttpScaleRule,
    Ingress,
    ManagedEnvironment,
    ManagedServiceIdentity,
    RegistryCredentials,
    Scale,
    ScaleRule,
    Secret,
    Template,
    WorkloadProfile,
)
from core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AzureContainerAppManager:
    def __init__(self):
        self.subscription_id = settings.azure_subscription_id
        self.resource_group = settings.azure_resource_group
        self.location = settings.azure_location

        self.credential = ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
        )

        self.client = ContainerAppsAPIClient(self.credential, self.subscription_id)

    def get_environment_id(
        self,
        env_name: str,
        use_gpu: bool = False,
    ):
        """Lấy hoặc tạo Managed Environment."""

        try:
            logger.info(f"Đang kiểm tra Environment: {env_name}...")

            workload_profiles = [
                WorkloadProfile(
                    name="Consumption",
                    workload_profile_type="Consumption",
                )
            ]

            if use_gpu:
                workload_profiles.append(
                    WorkloadProfile(
                        name="NC8as-T4",
                        workload_profile_type=("Consumption-GPU-NC8as-T4"),
                    )
                )

            env_payload = ManagedEnvironment(
                location=self.location,
                workload_profiles=workload_profiles,
            )

            poller = self.client.managed_environments.begin_create_or_update(
                self.resource_group,
                env_name,
                env_payload,
            )

            env = poller.result()

            logger.info(f"Environment sẵn sàng: {env.id}")

            return env.id

        except AzureError as e:
            logger.exception(f"Lỗi khi tạo Managed Environment: {e}")
            raise

    def create_or_update_app(
        self,
        env_name: str,
        image: str,
        cpu: float | None = None,
        memory: str | None = None,
        port: int = 8000,
        use_gpu: bool = False,
    ):
        """
        Deploy hoặc update Container App.

        Runtime environment variables của model-test được
        truyền vào Container App tại đây.
        """

        gpu_enabled = use_gpu or getattr(
            settings,
            "use_gpu",
            False,
        )

        env_id = self.get_environment_id(env_name)

        if gpu_enabled:
            workload_profile_name = "NC8as-T4"
            cpu = cpu if cpu is not None else 8.0
            memory = memory if memory is not None else "56Gi"

            logger.info("Deploy với SERVERLESS GPU " "(Consumption-GPU-NC8as-T4)")
        else:
            workload_profile_name = "Consumption"
            cpu = cpu if cpu is not None else 1.0
            memory = memory if memory is not None else "2Gi"

            logger.info("Deploy với SERVERLESS CPU")

        # ---------------------------------------------------------
        # ACA secrets
        # ---------------------------------------------------------
        #
        # Các giá trị này không được ghi trực tiếp vào image.
        # Container chỉ nhận chúng thông qua secret_ref.
        #
        registry_password_secret = Secret(
            name="registry-password",
            value=settings.registry_password,
        )

        object_storage_access_key_secret = Secret(
            name="object-storage-access-key",
            value=settings.object_storage_access_key,
        )

        object_storage_secret_key_secret = Secret(
            name="object-storage-secret-key",
            value=settings.object_storage_secret_key,
        )

        # ---------------------------------------------------------
        # Runtime environment variables
        # ---------------------------------------------------------
        #
        # Biến thường: dùng value
        # Biến nhạy cảm: dùng secret_ref
        #
        container_env = [
            # Object storage - non-secret
            EnvironmentVar(
                name="OBJECT_STORAGE_ENDPOINT",
                value=settings.object_storage_endpoint,
            ),
            EnvironmentVar(
                name="OBJECT_STORAGE_BUCKET",
                value=settings.object_storage_bucket,
            ),
            EnvironmentVar(
                name="OBJECT_STORAGE_REGION",
                value=settings.object_storage_region,
            ),
            EnvironmentVar(
                name="OBJECT_STORAGE_SECURE",
                value=str(settings.object_storage_secure).lower(),
            ),
            # Object storage - secret
            EnvironmentVar(
                name="OBJECT_STORAGE_ACCESS_KEY",
                secret_ref="object-storage-access-key",
            ),
            EnvironmentVar(
                name="OBJECT_STORAGE_SECRET_KEY",
                secret_ref="object-storage-secret-key",
            ),
        ]

        # ---------------------------------------------------------
        # Container App payload
        # ---------------------------------------------------------

        container_app_config = ContainerApp(
            location=self.location,
            environment_id=env_id,
            workload_profile_name=workload_profile_name,
            identity=ManagedServiceIdentity(
                type="SystemAssigned",
            ),
            configuration=Configuration(
                secrets=[
                    registry_password_secret,
                    object_storage_access_key_secret,
                    object_storage_secret_key_secret,
                ],
                registries=[
                    RegistryCredentials(
                        server=settings.registry_server,
                        username=settings.registry_username,
                        password_secret_ref=("registry-password"),
                    ),
                ],
                ingress=Ingress(
                    external=True,
                    target_port=port,
                    transport="http",
                    allow_insecure=False,
                ),
            ),
            template=Template(
                containers=[
                    Container(
                        name="model-test",
                        image=image,
                        # Đây là phần inject env vào image
                        env=container_env,
                        resources=ContainerResources(
                            cpu=cpu,
                            memory=memory,
                        ),
                    ),
                ],
                scale=Scale(
                    min_replicas=0,
                    max_replicas=1,
                    rules=[
                        ScaleRule(
                            name="http-training",
                            http=HttpScaleRule(
                                metadata={
                                    "concurrentRequests": "1",
                                },
                            ),
                        ),
                    ],
                ),
            ),
        )

        try:
            logger.info("Đang deploy Container App " f"[{settings.app_name}]...")

            poller = self.client.container_apps.begin_create_or_update(
                self.resource_group,
                settings.app_name,
                container_app_config,
            )

            result = poller.result()

            fqdn = None

            if result.configuration and result.configuration.ingress:
                fqdn = result.configuration.ingress.fqdn

            logger.info("Deploy thành công. " f"FQDN: {fqdn}")

            return {
                "name": result.name,
                "fqdn": fqdn,
                "provisioning_state": (result.provisioning_state),
            }

        except AzureError as exc:
            logger.exception(f"Lỗi Azure khi deploy: {exc}")
            return None

    def stop_app_completely(self) -> bool:
        """Dừng Container App bằng cách deactivate tất cả các active revision."""
        try:
            logger.info(
                f"Bắt đầu dừng Container App: {settings.app_name} "
                "trong RG: {self.resource_group}"
            )

            revisions = self.client.container_apps_revisions.list_revisions(
                resource_group_name=self.resource_group,
                container_app_name=settings.app_name,
            )

            deactivated_count = 0

            for rev in revisions:
                if rev.active:
                    logger.info(f"Đang deactivate revision: {rev.name}...")
                    self.client.container_apps_revisions.deactivate_revision(
                        resource_group_name=self.resource_group,
                        container_app_name=settings.app_name,
                        revision_name=rev.name,
                    )
                    deactivated_count += 1

            if deactivated_count == 0:
                logger.info(
                    f"Container App '{settings.app_name}' hiện đã tắt từ trước."
                )
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
                logger.warning(
                    f"Không tìm thấy revision nào cho App: {settings.app_name}"
                )
                return False

            logger.info(f"Đang activate revision mới nhất: {latest_revision_name}...")

            self.client.container_apps_revisions.activate_revision(
                resource_group_name=self.resource_group,
                container_app_name=settings.app_name,
                revision_name=latest_revision_name,
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
                "latest_revision": app.latest_revision_name,
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin app: {e}")
            return None
