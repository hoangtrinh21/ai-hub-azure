from core.container_app_manager import AzureContainerAppManager
from core.settings import settings

if __name__ == "__main__":
    manager = AzureContainerAppManager()

    app_info = manager.create_or_update_app(
        env_name=settings.azure_container_env,
        image=settings.container_image,
        cpu=settings.container_cpu,
        memory=settings.container_memory,
        port=8000,
        use_gpu=settings.use_gpu,
    )

    if not app_info:
        raise SystemExit("Deploy Container App thất bại.")

    fqdn = app_info["fqdn"]

    print("=" * 70)
    print("ACA DEPLOY SUCCESS")
    print("=" * 70)
    print(f"App:       {app_info['name']}")
    print(f"Status:    {app_info['provisioning_state']}")
    print(f"FQDN:      https://{fqdn}")
    print(f"Health:    https://{fqdn}/healthz")
    print(f"Docs:      https://{fqdn}/docs")
    print(f"Train:     POST https://{fqdn}/train")
    print(f"Predict:   POST https://{fqdn}/predict")
    print(f"Models:    GET https://{fqdn}/models")
    print("=" * 70)
