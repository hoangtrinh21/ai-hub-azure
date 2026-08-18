import os
import time
import psutil
import numpy as np
from fastapi import FastAPI, Query
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification

app = FastAPI(
    title="ML Stress Test API",
    description="API kiểm thử quá tải CPU và RAM phục vụ theo dõi Cloud Metrics"
)

def get_system_metrics():
    """Hàm lấy thông số CPU và RAM hiện tại"""
    mem = psutil.virtual_memory()
    return {
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
        "ram_used_mb": round(mem.used / (1024 * 1024), 2),
        "ram_total_mb": round(mem.total / (1024 * 1024), 2),
        "ram_percent": mem.percent
    }


@app.get("/metrics")
def metrics():
    """Xem nhanh tình trạng CPU và RAM hiện tại của server"""
    return get_system_metrics()


@app.post("/stress-train")
def stress_train(
    n_samples: int = Query(200_000, description="Số lượng dòng (Tăng cái này để ăn RAM)"),
    n_features: int = Query(50, description="Số lượng cột (Tăng cái này để ăn RAM)"),
    n_estimators: int = Query(100, description="Số lượng cây (Tăng cái này để ép CPU chạy lâu hơn)"),
    target_ram_mb: int = Query(500, description="RAM giả lập bổ sung (MB) muốn ép chiếm giữ")
):
    """
    Endpoint ép full 100% CPU và chiếm RAM:
    - n_samples & target_ram_mb: Tăng dung lượng RAM tiêu thụ.
    - n_estimators: Tăng thời gian CPU chạy 100%.
    """
    start_time = time.time()
    initial_metrics = get_system_metrics()

    # 1. ÉP RAM: Cấp phát một mảng NumPy lớn trong bộ nhớ
    # Mỗi float64 tốn 8 bytes => (target_ram_mb * 1024 * 1024) / 8 phần tử
    ram_stress_array = None
    if target_ram_mb > 0:
        num_elements = int((target_ram_mb * 1024 * 1024) / 8)
        ram_stress_array = np.ones(num_elements, dtype=np.float64)

    # Sinh tập dữ liệu ML lớn
    X, y = make_classification(
        n_samples=n_samples, 
        n_features=n_features, 
        n_informative=int(n_features * 0.8),
        random_state=42
    )

    peak_ram_metrics = get_system_metrics()

    # 2. ÉP CPU: n_jobs=-1 sẽ kích hoạt TẤT CẢ các CPU Cores/vCPU lên 100%
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        n_jobs=-1,  # Sử dụng tối đa tất cả các nhân CPU có sẵn
        random_state=42
    )
    
    # Bắt đầu quá trình Train nặng
    model.fit(X, y)
    
    total_time = round(time.time() - start_time, 2)
    final_metrics = get_system_metrics()

    # Giải phóng mảng RAM sau khi train xong
    del ram_stress_array
    del X
    del y

    return {
        "status": "success",
        "time_taken_seconds": total_time,
        "parameters": {
            "n_samples": n_samples,
            "n_features": n_features,
            "n_estimators": n_estimators,
            "allocated_ram_stress_mb": target_ram_mb
        },
        "metrics_before": initial_metrics,
        "metrics_during_stress": peak_ram_metrics,
        "metrics_after": final_metrics
    }