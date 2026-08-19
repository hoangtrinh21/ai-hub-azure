# AI Model Deployment on Azure Container Apps (ACA)

Dự án cung cấp giải pháp đóng gói, huấn luyện và phục vụ (serving) **Model Machine Learning với FastAPI**, kết hợp công cụ tự động hóa triển khai (submit) lên **Azure Container Apps (ACA)** có hỗ trợ scale-to-zero và quản lý tài nguyên.


## Tài liệu hướng dẫn

Toàn bộ tài liệu chi tiết về dự án đã được chuyển vào thư mục `docs/`. 

## Cấu Trúc Dự Án

```text
.
├── model-test/    # Source code FastAPI: Train, Predict, Quản lý Model
├── submit/        # Tool/Script tự động hóa deploy lên Azure (SDK/CLI)
└── docs/          # TÀI LIỆU HƯỚNG DẪN CHI TIẾT
```

## Bắt Đầu Nhanh (Quick Start)

1. **Chuẩn bị Model API (Local Test):**
   ```bash
   cd model-test
   docker build -t ml-test-app:local .
   docker run -p 8000:8000 --env-file .env ml-test-app:local
   ```

2. **Cấu hình thông tin Azure & Deploy:**
   - Cập nhật thông tin Service Principal, Registry và Storage vào file `submit/.env`.
   - Chạy script submit tự động:
   ```bash
   cd submit
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python main.py
   ```
---
