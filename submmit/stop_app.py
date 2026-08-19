from submmit.core.container_app_manager import AzureContainerAppManager
from submmit.core.settings import settings

if __name__ == "__main__":
    manager = AzureContainerAppManager()
    
    print(f"Đang gọi lệnh tắt Container App: {settings.app_name}...")
    success = manager.stop_app_completely()
    
    if success:
        print("Container đã được tắt hoàn toàn! Bạn sẽ không tốn chi phí nữa.")
    else:
        print("Không thể tắt container. Vui lòng kiểm tra lại log hoặc tắt thủ công trên Azure Portal.")