from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from app.core.config import settings


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


class StorageConfigError(RuntimeError):
    pass


class TaskImageStorage:
    def upload_image(self, content: bytes, content_type: str, filename: str = "") -> str:
        if not settings.minio_endpoint or not settings.minio_access_key or not settings.minio_secret_key:
            raise StorageConfigError("MinIO is not configured.")
        if not settings.minio_public_base_url:
            raise StorageConfigError("MINIO_PUBLIC_BASE_URL is not configured.")
        if len(content) > settings.task_image_max_bytes:
            raise ValueError("Image is too large.")

        extension = ALLOWED_IMAGE_TYPES.get(content_type.lower())
        if extension is None:
            extension = _extension_from_filename(filename)
        if extension not in {"jpg", "jpeg", "png", "webp", "gif"}:
            raise ValueError("Unsupported image type.")
        if extension == "jpeg":
            extension = "jpg"

        try:
            from minio import Minio
        except ImportError as exc:
            raise StorageConfigError("MinIO SDK is not installed.") from exc

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        object_name = f"task-images/{uuid4().hex}.{extension}"
        client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        return f"{settings.minio_public_base_url.rstrip('/')}/{object_name}"


def _extension_from_filename(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].strip().lower()
