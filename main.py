from core.container_app_manager import AzureContainerAppManager
from core.settings import settings

if __name__ == "__main__":
    manager = AzureContainerAppManager()

    IMAGE_NAME = "docker.io/trinhhoang01/ml-test-app:v2"

    print(f"Bắt đầu triển khai Container để Test Training 1 lần...")
    
    app_info = manager.create_or_update_app(
        env_name=settings.azure_container_env,
        image=IMAGE_NAME,
        cpu=1.0,
        memory="2.0Gi",
        port=8000
    )

    if app_info:
        print("\n" + "="*60)
        print(f"ĐÃ KÍCH HOẠT CONTAINER THÀNH CÔNG!")
        print(f"App Name: {app_info['name']}")
        print(f"Status:   {app_info['provisioning_state']}")
        print(f"Tên miền ứng dụng: https://{app_info['fqdn']}")
        print("="*60)
        print("\nBƯỚC TIẾP THEO ĐỂ XEM ĐÃ TRAIN XONG CHƯA:")
        print(f"1. Mở Azure Portal -> Vào Container App '{app_info['name']}'.")
        print("2. Vào menu bên trái: Monitoring -> Log stream để xem log train.")
        print("3. Khi thấy log báo Train xong, hãy chạy file `python stop_app.py` để TẮT CONTAINER tránh bị lặp lại và tiết kiệm tiền.")
        print("="*60)