from datetime import datetime
from typing import Iterator

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class ObjectStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        secure: bool = True,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            use_ssl=secure,
            config=Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": "path",
                },
            ),
        )

    def check_bucket(self) -> None:
        """
        Kiểm tra bucket tồn tại và có quyền truy cập.

        Nên tạo bucket trước trên object storage.
        """
        self.client.head_bucket(Bucket=self.bucket)

    def upload_file(
        self,
        local_file_path: str,
        object_name: str,
    ) -> None:
        self.client.upload_file(
            Filename=local_file_path,
            Bucket=self.bucket,
            Key=object_name,
            ExtraArgs={
                "ContentType": "application/octet-stream",
            },
        )

    def object_exists(self, object_name: str) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=object_name,
            )
            return True
        except ClientError as exc:
            error_code = str(
                exc.response.get("Error", {}).get("Code", "")
            )

            if error_code in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False

            raise

    def download_file(
        self,
        object_name: str,
        local_file_path: str,
    ) -> None:
        self.client.download_file(
            Bucket=self.bucket,
            Key=object_name,
            Filename=local_file_path,
        )

    def download_stream(
        self,
        object_name: str,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=object_name,
        )

        body = response["Body"]

        try:
            while True:
                chunk = body.read(chunk_size)

                if not chunk:
                    break

                yield chunk
        finally:
            body.close()

    def delete_object(self, object_name: str) -> None:
        self.client.delete_object(
            Bucket=self.bucket,
            Key=object_name,
        )

    def list_objects(
        self,
        prefix: str = "",
    ) -> list[dict]:
        """
        Liệt kê toàn bộ object, có hỗ trợ pagination.
        """
        objects: list[dict] = []
        continuation_token = None

        while True:
            params = {
                "Bucket": self.bucket,
                "Prefix": prefix,
            }

            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = self.client.list_objects_v2(**params)

            for item in response.get("Contents", []):
                objects.append(
                    {
                        "key": item["Key"],
                        "size": item["Size"],
                        "last_modified": item["LastModified"],
                    }
                )

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get(
                "NextContinuationToken"
            )

            if not continuation_token:
                break

        return objects

    def get_latest_model(
        self,
        prefix: str = "models/",
    ) -> dict | None:
        objects = self.list_objects(prefix=prefix)

        model_objects = [
            item
            for item in objects
            if item["key"].endswith(".joblib")
        ]

        if not model_objects:
            return None

        return max(
            model_objects,
            key=lambda item: (
                item["last_modified"]
                if isinstance(
                    item["last_modified"],
                    datetime,
                )
                else datetime.min
            ),
        )

    def create_presigned_download_url(
        self,
        object_name: str,
        expires_in: int = 3600,
    ) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_name,
            },
            ExpiresIn=expires_in,
        )