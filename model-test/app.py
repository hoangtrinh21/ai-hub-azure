import gc
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
import psutil
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier

from core.object_storage import ObjectStorage
from core.settings import settings


# ---------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------

MODEL_DIR = Path(settings.model_dir)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

PROCESS = psutil.Process(os.getpid())
CPU_COUNT = os.cpu_count() or 1

TRAINING_LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()

loaded_model: RandomForestClassifier | None = None
model_metadata: dict[str, Any] = {}

object_storage = ObjectStorage(
    endpoint=settings.object_storage_endpoint,
    access_key=settings.object_storage_access_key,
    secret_key=settings.object_storage_secret_key,
    bucket=settings.object_storage_bucket,
    region=settings.object_storage_region,
    secure=settings.object_storage_secure,
)


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------

class PredictRequest(BaseModel):
    """
    Một mẫu dữ liệu.

    Với model train bằng n_features=20,
    features phải có đúng 20 số.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "features": [
                    0.1,
                    0.2,
                    0.3,
                    0.4,
                    0.5,
                    0.6,
                    0.7,
                    0.8,
                    0.9,
                    1.0,
                    1.1,
                    1.2,
                    1.3,
                    1.4,
                    1.5,
                    1.6,
                    1.7,
                    1.8,
                    1.9,
                    2.0,
                ]
            }
        }
    )

    features: list[float] = Field(
        ...,
        min_length=1,
        description=(
            "Một mảng phẳng gồm đúng số feature "
            "mà model yêu cầu. Ví dụ model yêu cầu "
            "20 features thì gửi đúng 20 số."
        ),
    )


class BatchPredictRequest(BaseModel):
    """
    Nhiều mẫu dữ liệu.
    Mỗi sample phải có cùng số lượng feature.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "samples": [
                    [
                        0.1,
                        0.2,
                        0.3,
                        0.4,
                        0.5,
                        0.6,
                        0.7,
                        0.8,
                        0.9,
                        1.0,
                        1.1,
                        1.2,
                        1.3,
                        1.4,
                        1.5,
                        1.6,
                        1.7,
                        1.8,
                        1.9,
                        2.0,
                    ],
                    [
                        1.1,
                        1.2,
                        1.3,
                        1.4,
                        1.5,
                        1.6,
                        1.7,
                        1.8,
                        1.9,
                        2.0,
                        2.1,
                        2.2,
                        2.3,
                        2.4,
                        2.5,
                        2.6,
                        2.7,
                        2.8,
                        2.9,
                        3.0,
                    ],
                ]
            }
        }
    )

    samples: list[list[float]] = Field(
        ...,
        min_length=1,
        description=(
            "Danh sách các sample. Mỗi sample phải có "
            "đúng số feature mà model yêu cầu."
        ),
    )


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def get_system_metrics() -> dict[str, Any]:
    process_memory = PROCESS.memory_info()
    system_memory = psutil.virtual_memory()

    return {
        "pid": os.getpid(),
        "cpu_count": CPU_COUNT,
        "process_cpu_percent": round(
            PROCESS.cpu_percent(interval=0.1),
            2,
        ),
        "process_ram_mb": round(
            process_memory.rss / 1024 / 1024,
            2,
        ),
        "system_ram_used_mb": round(
            system_memory.used / 1024 / 1024,
            2,
        ),
        "system_ram_total_mb": round(
            system_memory.total / 1024 / 1024,
            2,
        ),
        "system_ram_percent": system_memory.percent,
    }


def get_current_model():
    with MODEL_LOCK:
        model = loaded_model

    if model is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model chưa được load. "
                "Hãy gọi POST /train trước hoặc "
                "POST /models/latest/load."
            ),
        )

    return model


def get_expected_features(model) -> int:
    expected_features = getattr(
        model,
        "n_features_in_",
        None,
    )

    if expected_features is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không xác định được số lượng feature "
                "của model."
            ),
        )

    return int(expected_features)


def validate_sample(
    sample: list[float],
    expected_features: int,
    sample_index: int | None = None,
) -> None:
    if len(sample) != expected_features:
        prefix = ""

        if sample_index is not None:
            prefix = f"Sample index {sample_index}: "

        raise HTTPException(
            status_code=400,
            detail=(
                f"{prefix}model yêu cầu "
                f"{expected_features} features, "
                f"nhưng nhận được {len(sample)}. "
                f"Hãy gửi đúng {expected_features} số."
            ),
        )

    for feature_index, value in enumerate(sample):
        if not isinstance(value, (int, float)):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Feature index {feature_index} "
                    f"phải là số."
                ),
            )


def load_artifact_from_file(
    local_file_path: str,
) -> tuple[RandomForestClassifier, dict[str, Any]]:
    artifact = joblib.load(local_file_path)

    if not isinstance(artifact, dict):
        raise ValueError(
            "Model artifact phải có dạng dictionary."
        )

    if "model" not in artifact:
        raise ValueError(
            "Model artifact không có key 'model'."
        )

    model = artifact["model"]
    metadata = artifact.get("metadata", {})

    return model, metadata


def load_model_into_memory(
    local_file_path: str,
) -> dict[str, Any]:
    global loaded_model, model_metadata

    model, metadata = load_artifact_from_file(
        local_file_path
    )

    with MODEL_LOCK:
        loaded_model = model
        model_metadata = metadata

    return metadata


def validate_features(
    model: RandomForestClassifier,
    features: list[float],
) -> None:
    expected_features = getattr(
        model,
        "n_features_in_",
        None,
    )

    if (
        expected_features is not None
        and len(features) != expected_features
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Model yêu cầu {expected_features} features, "
                f"nhưng nhận được {len(features)}."
            ),
        )


# ---------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Chạy khi container khởi động và shutdown.

    Khi ACA scale từ 0 lên 1:
    1. Container khởi động.
    2. Kiểm tra object storage.
    3. Tải model mới nhất nếu có.
    4. App bắt đầu nhận request.
    """

    global loaded_model, model_metadata

    # Startup
    try:
        object_storage.check_bucket()
        print(
            "Object storage connection: OK. "
            f"bucket={settings.object_storage_bucket}"
        )
    except Exception as exc:
        print(
            "Object storage connection failed: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        latest_model = object_storage.get_latest_model()

        if latest_model is None:
            print("Chưa có model trên object storage.")
        else:
            startup_model_path = (
                MODEL_DIR / "startup-model.joblib"
            )

            object_storage.download_file(
                object_name=latest_model["key"],
                local_file_path=str(startup_model_path),
            )

            metadata = load_model_into_memory(
                str(startup_model_path)
            )

            startup_model_path.unlink(
                missing_ok=True
            )

            print(
                "Đã load model mới nhất: "
                f"{latest_model['key']}; "
                f"metadata={metadata}"
            )

    except Exception as exc:
        # Không làm container fail chỉ vì chưa có model
        # hoặc object storage tạm thời chưa sẵn sàng.
        print(
            "Không thể load model lúc startup: "
            f"{type(exc).__name__}: {exc}"
        )

    yield

    # Shutdown
    with MODEL_LOCK:
        loaded_model = None
        model_metadata = {}

    gc.collect()
    print("Application shutdown completed.")


app = FastAPI(
    title="ACA ML Training and Serving API",
    description=(
        "Train model, lưu object storage, serving prediction "
        "và download model."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "ACA ML Training and Serving API",
        "status": "running",
        "endpoints": {
            "health": "GET /healthz",
            "metrics": "GET /metrics",
            "train": "POST /train",
            "model_info": "GET /model",
            "predict": "POST /predict",
            "batch_predict": "POST /predict/batch",
            "list_models": "GET /models",
            "download": "GET /models/{model_id}/download",
            "presigned_url": (
                "GET /models/{model_id}/presigned-url"
            ),
            "reload_latest": "POST /models/latest/load",
        },
    }


@app.get("/healthz")
def healthz():
    with MODEL_LOCK:
        has_model = loaded_model is not None

    return {
        "status": "healthy",
        "model_loaded": has_model,
        "latest_model_metadata": model_metadata,
    }


@app.get("/metrics")
def metrics():
    return get_system_metrics()


# ---------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------

@app.post("/train")
@app.post("/stress-train")
def train_model(
    n_samples: int = Query(
        default=settings.default_n_samples,
        ge=1_000,
        le=1_000_000,
        description="Số lượng sample.",
    ),
    n_features: int = Query(
        default=settings.default_n_features,
        ge=2,
        le=200,
        description="Số lượng feature.",
    ),
    n_estimators: int = Query(
        default=settings.default_n_estimators,
        ge=1,
        le=500,
        description="Số lượng cây Random Forest.",
    ),
    target_ram_mb: int = Query(
        default=settings.default_target_ram_mb,
        ge=0,
        le=4_096,
        description="RAM bổ sung cần cấp phát.",
    ),
):
    """
    Train model, upload object storage và load model vào RAM.

    Đây là endpoint đồng bộ. Request giữ kết nối cho đến khi:
    - Training hoàn tất.
    - File model được tạo.
    - File model upload thành công.
    """

    global loaded_model, model_metadata

    if not TRAINING_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Một lượt training khác đang chạy.",
        )

    started_at = time.perf_counter()

    ram_stress_array = None
    X = None
    y = None
    trained_model = None
    local_model_path: Path | None = None

    try:
        metrics_before = get_system_metrics()

        # Cấp phát RAM để test metrics ACA.
        if target_ram_mb > 0:
            num_elements = (
                target_ram_mb
                * 1024
                * 1024
                // np.dtype(np.float32).itemsize
            )

            ram_stress_array = np.ones(
                num_elements,
                dtype=np.float32,
            )

        X, y = make_classification(
            n_samples=n_samples,
            n_features=n_features,
            n_informative=max(
                2,
                int(n_features * 0.8),
            ),
            n_redundant=0,
            n_repeated=0,
            n_classes=2,
            random_state=42,
        )

        X = X.astype(np.float32, copy=False)

        metrics_before_training = get_system_metrics()

        trained_model = RandomForestClassifier(
            n_estimators=n_estimators,
            n_jobs=-1,
            random_state=42,
        )

        training_started_at = time.perf_counter()

        trained_model.fit(X, y)

        training_time = round(
            time.perf_counter() - training_started_at,
            2,
        )

        metrics_after_training = get_system_metrics()

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")

        model_id = (
            f"random-forest-"
            f"{timestamp}-"
            f"{uuid4().hex[:8]}"
        )

        object_name = f"models/{model_id}.joblib"

        metadata = {
            "model_id": model_id,
            "object_name": object_name,
            "model_type": "RandomForestClassifier",
            "created_at": timestamp,
            "n_samples": n_samples,
            "n_features": n_features,
            "n_estimators": n_estimators,
            "target_ram_mb": target_ram_mb,
            "training_time_seconds": training_time,
            "pid": os.getpid(),
        }

        # Lưu model vào file tạm.
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".joblib",
            prefix=f"{model_id}-",
            dir=str(MODEL_DIR),
            delete=False,
        )

        local_model_path = Path(temp_file.name)
        temp_file.close()

        joblib.dump(
            {
                "model": trained_model,
                "metadata": metadata,
            },
            str(local_model_path),
            compress=3,
        )

        # Upload thành công trước khi bật model serving.
        object_storage.upload_file(
            local_file_path=str(local_model_path),
            object_name=object_name,
        )

        with MODEL_LOCK:
            loaded_model = trained_model
            model_metadata = metadata

        total_time = round(
            time.perf_counter() - started_at,
            2,
        )

        return {
            "status": "success",
            "message": (
                "Training, upload và serving model "
                "đã hoàn tất."
            ),
            "model_id": model_id,
            "object_name": object_name,
            "model_loaded": True,
            "training_time_seconds": training_time,
            "total_time_seconds": total_time,
            "parameters": {
                "n_samples": n_samples,
                "n_features": n_features,
                "n_estimators": n_estimators,
                "target_ram_mb": target_ram_mb,
            },
            "metrics_before": metrics_before,
            "metrics_before_training": metrics_before_training,
            "metrics_after_training": metrics_after_training,
            "endpoints": {
                "predict": "/predict",
                "download": (
                    f"/models/{model_id}/download"
                ),
                "presigned_url": (
                    f"/models/{model_id}/presigned-url"
                ),
            },
        }

    except MemoryError as exc:
        raise HTTPException(
            status_code=507,
            detail=(
                "Container không đủ RAM. "
                "Hãy giảm n_samples, n_features hoặc "
                "target_ram_mb."
            ),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Training hoặc upload thất bại: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    finally:
        if local_model_path is not None:
            local_model_path.unlink(missing_ok=True)

        del ram_stress_array
        del X
        del y
        del trained_model

        gc.collect()
        TRAINING_LOCK.release()


# ---------------------------------------------------------------------
# Model information and reload
# ---------------------------------------------------------------------

@app.get("/model")
def model_info():
    with MODEL_LOCK:
        has_model = loaded_model is not None
        metadata = dict(model_metadata)

    return {
        "model_loaded": has_model,
        "metadata": metadata,
    }


@app.post("/models/latest/load")
def load_latest_model():
    """
    Tải model mới nhất từ object storage vào RAM.
    Dùng khi startup load thất bại hoặc muốn reload thủ công.
    """
    latest_model = object_storage.get_latest_model()

    if latest_model is None:
        raise HTTPException(
            status_code=404,
            detail="Object storage chưa có model.",
        )

    local_model_path: Path | None = None

    try:
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".joblib",
            prefix="latest-",
            dir=str(MODEL_DIR),
            delete=False,
        )

        local_model_path = Path(temp_file.name)
        temp_file.close()

        object_storage.download_file(
            object_name=latest_model["key"],
            local_file_path=str(local_model_path),
        )

        metadata = load_model_into_memory(
            str(local_model_path)
        )

        return {
            "status": "success",
            "message": "Đã load model mới nhất vào RAM.",
            "object_name": latest_model["key"],
            "metadata": metadata,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Load model thất bại: {exc}",
        ) from exc

    finally:
        if local_model_path is not None:
            local_model_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------
# Prediction serving
# ---------------------------------------------------------------------

@app.post(
    "/predict",
    summary="Predict một sample",
    description=(
        "Gửi một sample dạng mảng phẳng. "
        "Số phần tử phải đúng bằng số feature của model."
    ),
)
def predict(request: PredictRequest):
    model = get_current_model()
    expected_features = get_expected_features(model)

    validate_sample(
        sample=request.features,
        expected_features=expected_features,
    )

    try:
        input_data = np.asarray(
            [request.features],
            dtype=np.float32,
        )

        predictions = model.predict(input_data)

        probabilities = None

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(
                input_data
            ).tolist()

        return {
            "status": "success",
            "count": 1,
            "features_per_sample": expected_features,
            "predictions": predictions.tolist(),
            "probabilities": probabilities,
            "model_metadata": model_metadata,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction thất bại: {exc}",
        ) from exc

    
@app.post(
    "/predict/batch",
    summary="Predict nhiều sample",
    description=(
        "Gửi nhiều sample. Mỗi sample phải có "
        "đúng số feature của model."
    ),
)
def predict_batch(request: BatchPredictRequest):
    model = get_current_model()
    expected_features = get_expected_features(model)

    for index, sample in enumerate(request.samples):
        validate_sample(
            sample=sample,
            expected_features=expected_features,
            sample_index=index,
        )

    try:
        input_data = np.asarray(
            request.samples,
            dtype=np.float32,
        )

        predictions = model.predict(input_data)

        probabilities = None

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(
                input_data
            ).tolist()

        return {
            "status": "success",
            "count": len(request.samples),
            "features_per_sample": expected_features,
            "predictions": predictions.tolist(),
            "probabilities": probabilities,
            "model_metadata": model_metadata,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Batch prediction thất bại: {exc}",
        ) from exc


@app.post(
    "/predict/example",
    summary="Predict bằng dữ liệu mẫu tự động",
)
def predict_example():
    """
    Endpoint dùng để test nhanh trên ACA/Swagger.
    Tự tạo đúng số lượng feature của model.
    """
    model = get_current_model()
    expected_features = get_expected_features(model)

    example_features = [
        round(index / 10, 4)
        for index in range(1, expected_features + 1)
    ]

    input_data = np.asarray(
        [example_features],
        dtype=np.float32,
    )

    try:
        predictions = model.predict(input_data)

        probabilities = None

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(
                input_data
            ).tolist()

        return {
            "status": "success",
            "message": "Prediction bằng dữ liệu mẫu thành công.",
            "features": example_features,
            "features_per_sample": expected_features,
            "predictions": predictions.tolist(),
            "probabilities": probabilities,
            "model_metadata": model_metadata,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Example prediction thất bại: {exc}",
        ) from exc


@app.get(
    "/model/input-schema",
    summary="Xem input schema của model",
)
def model_input_schema():
    model = get_current_model()
    expected_features = get_expected_features(model)

    return {
        "model_loaded": True,
        "model_type": type(model).__name__,
        "expected_features": expected_features,
        "request_format": {
            "features": [
                f"feature_{index}"
                for index in range(expected_features)
            ]
        },
    }


# ---------------------------------------------------------------------
# Download and object listing
# ---------------------------------------------------------------------

@app.get("/models")
def list_models():
    try:
        objects = object_storage.list_objects(
            prefix="models/"
        )

        return {
            "count": len(objects),
            "models": objects,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Không thể lấy danh sách model: {exc}",
        ) from exc


@app.get("/models/{model_id}/download")
def download_model(model_id: str):
    object_name = f"models/{model_id}.joblib"

    try:
        exists = object_storage.object_exists(
            object_name
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Không thể kiểm tra model: {exc}",
        ) from exc

    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy model: {model_id}",
        )

    return StreamingResponse(
        object_storage.download_stream(object_name),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{model_id}.joblib"'
            ),
        },
    )


@app.get("/models/{model_id}/presigned-url")
def create_presigned_url(
    model_id: str,
    expires_in: int = Query(
        default=3600,
        ge=60,
        le=86_400,
        description="Thời gian hết hạn URL, tính bằng giây.",
    ),
):
    object_name = f"models/{model_id}.joblib"

    try:
        exists = object_storage.object_exists(
            object_name
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Không thể kiểm tra model: {exc}",
        ) from exc

    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy model: {model_id}",
        )

    try:
        download_url = (
            object_storage.create_presigned_download_url(
                object_name=object_name,
                expires_in=expires_in,
            )
        )

        return {
            "model_id": model_id,
            "object_name": object_name,
            "expires_in_seconds": expires_in,
            "download_url": download_url,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Không thể tạo presigned URL: {exc}"
            ),
        ) from exc


@app.delete("/models/{model_id}")
def delete_model(model_id: str):
    object_name = f"models/{model_id}.joblib"

    if not object_storage.object_exists(object_name):
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy model: {model_id}",
        )

    try:
        object_storage.delete_object(object_name)

        return {
            "status": "deleted",
            "model_id": model_id,
            "object_name": object_name,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Xóa model thất bại: {exc}",
        ) from exc

def normalize_prediction_input(
    features: list[Any],
    expected_features: int,
) -> np.ndarray:
    """
    Chuẩn hóa input về numpy array dạng:

    [
        [x1, x2, ..., xn],
        [x1, x2, ..., xn],
    ]

    Hỗ trợ:
    - Một mẫu: [0.1, 0.2, ...]
    - Nhiều mẫu: [[...], [...]]
    """

    if not features:
        raise HTTPException(
            status_code=400,
            detail="features không được rỗng.",
        )

    first_item = features[0]

    # Trường hợp một mẫu:
    # {"features": [0.1, 0.2, ..., 2.0]}
    if isinstance(first_item, (int, float)):
        samples = [features]

    # Trường hợp nhiều mẫu:
    # {"features": [[...], [...]]}
    elif isinstance(first_item, list):
        samples = features

    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "features phải là danh sách số hoặc "
                "danh sách các danh sách số."
            ),
        )

    for index, sample in enumerate(samples):
        if not isinstance(sample, list):
            raise HTTPException(
                status_code=400,
                detail=f"Sample index {index} không hợp lệ.",
            )

        if len(sample) != expected_features:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Sample index {index} yêu cầu "
                    f"{expected_features} features, "
                    f"nhưng nhận được {len(sample)}."
                ),
            )

        for feature_index, value in enumerate(sample):
            if not isinstance(value, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Feature index {feature_index} "
                        f"của sample {index} phải là số."
                    ),
                )

    try:
        return np.asarray(
            samples,
            dtype=np.float32,
        )

    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Không thể chuyển features thành số: {exc}",
        ) from exc
