# 📖 Hướng Dẫn Quản Lý & Tự Động Hóa Triển Khai Azure Container Apps

Tài liệu này hướng dẫn thiết lập hạ tầng trên **Azure Portal**, cấu hình biến môi trường và sử dụng mã nguồn Python (Azure SDK) để quản lý, triển khai các Container phục vụ mục đích **Training Model AI** hoặc **Chạy Web API Service** trên hạ tầng Azure Container Apps.

---

## 📌 MỤC LỤC
1. [Cấu Trúc Thư Mục Dự Án](#-cấu-trúc-thư-mục-dự-án)
2. [Lấy Azure Tenant ID, Client ID và Client Secret](#1-lấy-azure-tenant-id-client-id-và-client-secret)
3. [Lấy Subscription ID & Phân Quyền RBAC](#2-lấy-subscription-id--phân-quyền-rbac)
4. [Lấy Thông Tin Private Registry](#3-lấy-thông-tin-private-registry)
5. [Kiểm Tra Danh Sách Location (Region) Được Phép Hợp Lệ](#4-kiểm-tra-danh-sách-location-region-được-phép-hợp-lệ)
6. [Đăng Ký Resource Providers Bắt Buộc](#5-đăng-ký-resource-providers-bắt-buộc)
7. [Mẫu Cấu Hình Biến Môi Trường (.env)](#6-mẫu-cấu-hình-biến-môi-trường-env)
8. [Hướng Dẫn Vận Hành & Quy Trình Chạy](#7-hướng-dẫn-vận-hành--quy-trình-chạy)
9. [Cách Lấy Tên Miền (Application URL) & Lưu Ý Ingress](#8-cách-lấy-tên-miền-application-url--lưu-ý-ingress)
10. [Xử Lý Các Lỗi Thường Gặp (Troubleshooting)](#9-xử-lý-các-lỗi-thường-gặp-troubleshooting)

---

## 📂 CẤU TRÚC THƯ MỤC DỰ ÁN

```text
azure-container-app/
├── core/
│   ├── __init__.py
│   ├── settings.py                # Quản lý cấu hình biến môi trường
│   └── container_app_manager.py   # Lớp xử lý giao tiếp Azure SDK
├── .env                           # Lưu trữ thông tin xác thực & cấu hình
├── main.py                        # Script thực thi deploy/chạy ứng dụng
├── stop_app.py                    # Script dừng container để ngắt tính phí
└── requirements.txt               # Thư viện phụ thuộc
```

---

## 1. Lấy Azure Tenant ID, Client ID và Client Secret

Để phần mềm Python giao tiếp được với Azure API, hệ thống cần tạo một **Service Principal** (Tài khoản định danh cho ứng dụng).

### Bước 1.1: Tạo App Registration
1. Truy cập [Azure Portal](https://portal.azure.com/).
2. Trên thanh tìm kiếm, chọn **Microsoft Entra ID** (trước đây là Azure Active Directory).
3. Tại menu bên trái, chọn **App registrations** ➔ Nhấn **+ New registration**.
4. Điền các thông tin:
   * **Name**: `AI-Hub-Manager` (hoặc tên nhận diện bất kỳ).
   * **Supported account types**: Chọn *Accounts in this organizational directory only (Single tenant)*.
5. Nhấn **Register**.

### Bước 1.2: Sao Chép Tenant ID & Client ID
1. Màn hình tự động chuyển tới trang **Overview** của App vừa tạo.
2. Sao chép 2 giá trị:
   * 📋 **Application (client) ID** ➔ Dùng cho `AZURE_CLIENT_ID`
   * 📋 **Directory (tenant) ID** ➔ Dùng cho `AZURE_TENANT_ID`

### Bước 1.3: Tạo Client Secret
1. Tại menu bên trái của App, chọn **Certificates & secrets**.
2. Chọn tab **Client secrets** ➔ Nhấn **+ New client secret**.
3. Điền **Description** ➔ Nhấn **Add**.
4. ⚠️ **LƯU Ý CỰC KỲ QUAN TRỌNG:**
   * Sao chép ngay chuỗi ký tự tại cột **VALUE** (chứ **KHÔNG** copy cột *Secret ID*).
   * Giá trị `Value` chỉ hiển thị **1 lần duy nhất** tại thời điểm tạo.
   * 📋 **Value** ➔ Dùng cho `AZURE_CLIENT_SECRET`

---

## 2. Lấy Subscription ID & Phân Quyền RBAC

### Bước 2.1: Lấy Subscription ID
1. Gõ **Subscriptions** trên thanh tìm kiếm của Azure Portal ➔ Chọn **Subscriptions**.
2. Sao chép chuỗi mã tại cột **Subscription ID**.
   * 📋 **Subscription ID** ➔ Dùng cho `AZURE_SUBSCRIPTION_ID`

### Bước 2.2: Phân Quyền Contributor Cho Service Principal
1. Bấm trực tiếp vào tên Subscription cần cấu hình.
2. Tại menu bên trái, chọn **Access control (IAM)**.
3. Nhấn **+ Add** ➔ Chọn **Add role assignment**.
4. Tại tab **Role**: Tìm và chọn role **Contributor** (Người đóng góp) ➔ Nhấn **Next**.
5. Tại tab **Members**:
   * Chọn *User, group, or service principal*.
   * Nhấn **+ Select members**.
   * Tìm tên App đã tạo ở Bước 1.1 (`AI-Hub-Manager`) ➔ Chọn app ➔ Nhấn **Select**.
6. Nhấn **Review + assign** để hoàn tất gán quyền.

---

## 3. Lấy Thông Tin Private Registry

Khi Container App tải ảnh Docker (Image) về triển khai, hệ thống cần thông tin đăng nhập vào Registry.

### Trường hợp A: Sử dụng Azure Container Registry (ACR)
1. Trên Azure Portal, truy cập dịch vụ **Container registries** ➔ Bấm vào ACR tương ứng.
2. Tại menu bên trái ➔ Chọn **Access keys**.
3. Bật công tắc **Admin user** sang `Enable`.
4. Copy các giá trị:
   * `Login server` (Ví dụ: `myregistry.azurecr.io`) ➔ `REGISTRY_SERVER`
   * `Username` ➔ `REGISTRY_USERNAME`
   * `password` ➔ `REGISTRY_PASSWORD`

### Trường hợp B: Sử dụng Private Registry Riêng (VNPT / Docker Hub / Custom)
1. **`REGISTRY_SERVER`**: Tên miền host của Registry (**KHÔNG** chứa `https://` hoặc dấu `/` ở cuối).
   * *Ví dụ:* `ai-repository.vnpt.vn` hoặc `docker.io`
2. **`REGISTRY_USERNAME`**: Tài khoản đăng nhập Registry.
3. **`REGISTRY_PASSWORD`**: Mật khẩu hoặc Access Token của Registry.

---

## 4. Kiểm Tra Danh Sách Location (Region) Được Phép Hợp Lệ

Một số loại tài khoản Azure (như *Azure for Students* hoặc tài khoản Enterprise) có áp dụng **Azure Policy** giới hạn cụ thể các Vùng (Region) được phép tạo tài nguyên.

### Các bước kiểm tra danh sách Region được phép:
1. Đăng nhập vào [Azure Portal](https://portal.azure.com/).
2. Nhập **Policy** vào thanh tìm kiếm trên cùng ➔ Chọn dịch vụ **Policy**.
3. Tại menu bên trái, chọn mục **Assignments**.
4. Chọn chính sách có tên: **`Allowed resource deployment regions`**.
5. Chọn tab **Parameters** ➔ Xem danh sách các Region được phép tại dòng **`listOfAllowedLocations`** (cột *Parameter value*).

> **Gợi ý các Region tối ưu gần Việt Nam thường có trong danh sách cho phép:**
> * `eastasia` (Hong Kong) - *Khuyên dùng: Tốc độ cao, băng thông tốt*
> * `japaneast` (Tokyo, Nhật Bản) - *Hạ tầng rất mạnh*
> * `koreacentral` (Seoul, Hàn Quốc)

---

## 5. Đăng Ký Resource Providers Bắt Buộc

Mặc định, tài khoản Azure mới chưa bật sẵn các dịch vụ Container. Việc kích hoạt 2 dịch vụ dưới đây là bắt buộc (thực hiện 1 lần duy nhất):

1. Vào **Subscriptions** ➔ Chọn Subscription tương ứng.
2. Tại menu bên trái, chọn **Settings** ➔ Chọn **Resource providers**.
3. Tìm kiếm và chọn từng provider sau, nếu trạng thái chưa phải `Registered` thì nhấn **Register**:
   * **`Microsoft.App`** (Dịch vụ quản lý Container Apps)
   * **`Microsoft.OperationalInsights`** (Dịch vụ theo dõi Log Analytics)

---

## 6. Mẫu Cấu Hình Biến Môi Trường (.env)

Sau khi thu thập đầy đủ các thông số ở các bước trên, tiến hành điền vào file `.env` tại thư mục gốc dự án:

```env
# 1. Cấu hình Xác thực Azure
AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=xxxx

# 2. Cấu hình Môi trường Container
AZURE_RESOURCE_GROUP=AI-Hub-RG
AZURE_LOCATION=eastasia
AZURE_CONTAINER_ENV=ai-hub-env

# 3. Cấu hình Docker Registry
REGISTRY_SERVER=xxxx
REGISTRY_USERNAME=xxxx
REGISTRY_PASSWORD=xxxx

# 4. Cấu hình Object storage
OBJECT_STORAGE_ENDPOINT=xxxx
OBJECT_STORAGE_ACCESS_KEY=xxxx
OBJECT_STORAGE_SECRET_KEY=xxxx
OBJECT_STORAGE_BUCKET=xxxx
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_SECURE=true
```

---

## 7. Hướng Dẫn Vận Hành & Quy Trình Chạy

### Bước 7.1: Cài đặt phụ thuộc
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Bước 7.2: Kích hoạt chạy Container (`main.py`)
Thực hiện lệnh bên dưới để khởi tạo hạ tầng và kéo ảnh Docker về chạy:
```bash
python main.py
```

### Bước 7.3: Theo dõi tiến trình Training Model
1. Truy cập [Azure Portal](https://portal.azure.com/).
2. Tìm và chọn **Container Apps** ➔ Chọn App đang chạy (Ví dụ: `ai-hub-semi`).
3. Mở menu bên trái: chọn **Monitoring** ➔ **Log stream** để xem log in ra theo thời gian thực (realtime).
4. Tiến trình được coi là hoàn tất khi:
   * Log hiển thị hoàn thành các Epochs / Báo lưu weights thành công.
   * Biểu đồ **Metrics** ➔ **CPU Usage** giảm tụt về gần 0%.

### Bước 7.4: Dừng Container để ngắt tính phí (`stop_app.py`)
Khi tiến trình Training hoàn tất, thực hiện chạy lệnh dừng khẩn cấp để đưa số lượng Replicas về 0, ngắt hoàn toàn chi phí phát sinh:
```bash
python stop_app.py
```

---

## 8. Cách Lấy Tên Miền (Application URL) & Lưu Ý Ingress

### 8.1. Cách lấy URL truy cập
Nếu container triển khai dịch vụ Web API (FastAPI, Flask...), Azure sẽ cấp một tên miền FQDN chuẩn HTTPS:
`https://<ten-app>.<chuoi-ngau-nhien>.<region>.azurecontainerapps.io`

* **Cách 1 (Qua Code):** Kết quả trả về của hàm `create_or_update_app()` chứa thuộc tính `app_info['fqdn']`.
* **Cách 2 (Qua Portal):** Vào trang **Overview** của Container App ➔ Xem tại mục **Application Url**.

### 8.2. Giải thích trường hợp `Application Url: Ingress disabled`
Nếu trang Overview hiển thị `Ingress disabled`:
* **Trường hợp Container chỉ Train Model (Batch Script):** Đây là hiện tượng bình thường. Do script Python kết thúc không mở Web Server ở cổng HTTP (80/8080), Envoy Proxy sẽ ghi nhận cổng không hoạt động. Quá trình training vẫn diễn ra bình thường ngầm bên trong.
* **Trường hợp Container là Web API:** Cần kiểm tra lại cấu hình code Python trong Docker xem đã chạy server (Uvicorn/Gunicorn) lắng nghe đúng cổng truyền vào hay chưa, và điều chỉnh tham số `transport="http"`, `allow_insecure=True` trong đối tượng `Ingress`.

---

## 9. Xử Lý Các Lỗi Thường Gặp (Troubleshooting)

| Báo Lỗi (Error Message) | Nguyên Nhân | Cách Khắc Phục |
| :--- | :--- | :--- |
| `ManagedEnvironmentScheduledForDelete` | Môi trường `AZURE_CONTAINER_ENV` cũ đang trong quá trình xóa ngầm trên Azure (mất 5-15 phút). | Mở file `.env`, đổi tên `AZURE_CONTAINER_ENV` thành tên mới (ví dụ: `ai-hub-env-v2`). |
| `MaxNumberOfRegionalEnvironmentsInSubExceeded` | Hạn ngạch (Quota) cước phí giới hạn tối đa 1 Environment trên 1 Vùng (Region). | Mở file `.env`, đổi `AZURE_LOCATION` sang một Region khác (ví dụ: từ `indonesiacentral` sang `eastasia`). |
| `RequestDisallowedByAzure` | Region được chọn nằm ngoài danh sách cho phép của Azure Policy trên tài khoản. | Kiểm tra mục **Policy** trên Portal (theo Mục 4) và đổi `AZURE_LOCATION` về đúng Region được cấp phép. |
| `AADSTS7000215: Invalid client secret` | Copy nhầm **Secret ID** thay vì copy giá trị cột **Secret Value**. | Vào lại *App Registration* ➔ *Certificates & secrets* ➔ Tạo Secret mới và sao chép đúng cột **Value**. |
| `AuthorizationFailed` | Service Principal chưa được cấp quyền quản lý tài nguyên. | Vào Subscription ➔ *Access control (IAM)* ➔ Gán quyền **Contributor** cho App Registration. |
