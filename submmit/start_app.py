from core.container_app_manager import AzureContainerAppManager
from core.settings import settings

if __name__ == "__main__":
    manager = AzureContainerAppManager()

    print(f"Đang gọi lệnh bật Container App: {settings.app_name}...")
    success = manager.start_app()

    if success:
        print("Container đã được bật hoàn toàn!.")
    else:
        print(
            "Không thể tắt container. "
            "Vui lòng kiểm tra lại log hoặc tắt thủ công trên Azure Portal."
        )
