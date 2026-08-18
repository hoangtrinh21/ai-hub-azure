FROM python:3.11-slim

# Ngăn Python tạo file .pyc và bật log realtime ra terminal
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Cài thư viện trước để tận dụng Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào image
COPY . .

# Mở port (Cloud thường nhận port qua biến môi trường hoặc cổng mặc định 8000)
EXPOSE 8000

# Chạy server với host 0.0.0.0 để cho phép truy cập từ bên ngoài
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]