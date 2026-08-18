from container_app_manager import AzureContainerAppManager


if __name__ == "__main__":
    # Các thông số này nên lấy từ file .env
    SUB_ID = "your-id-here"
    RG = "AI-Hub-Resources"
    LOC = "eastus"

    manager = AzureContainerAppManager(SUB_ID, RG, LOC)

    # 1. Tạo một AI Worker model (ví dụ dùng image của bạn trên Docker Hub)
    app_info = manager.create_or_update_app(
        app_name="phi3-mini-worker",
        env_name="ai-hub-env",
        image="mcr.microsoft.com/azuredocs/containerapps-helloworld:latest", # Thay bằng image AI của bạn
        cpu=1.0,
        memory="2.0Gi"
    )

    if app_info:
        print(f"App của bạn đã sẵn sàng tại: {app_info['fqdn']}")

    # 2. Xem danh sách các app đang chạy
    all_apps = manager.list_apps()
    print(f"Các ứng dụng hiện có: {all_apps}")

    # 3. Xóa app khi không cần thiết
    # manager.delete_app("phi3-mini-worker")