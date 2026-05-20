from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from urllib.parse import quote, unquote
from uuid import uuid4

from app.core.config import settings


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

ALLOWED_FILE_TYPES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/zip": "zip",
}

ALLOWED_ATTACHMENT_TYPES = {**ALLOWED_IMAGE_TYPES, **ALLOWED_FILE_TYPES}
ATTACHMENT_PREFIX = "attachments"
TASK_IMAGE_PREFIX = "task-images"


class StorageConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredImage:
    content: bytes
    content_type: str


@dataclass(frozen=True)
class StoredAttachment:
    content: bytes
    content_type: str
    filename: str
    is_image: bool


@dataclass(frozen=True)
class AttachmentUpload:
    object_name: str
    filename: str
    content_type: str
    size: int
    is_image: bool


class AttachmentStorage:
    def upload_attachment(
        self,
        content: bytes,
        content_type: str,
        filename: str = "",
        *,
        prefix: str = ATTACHMENT_PREFIX,
        max_bytes: int | None = None,
    ) -> AttachmentUpload:
        if not settings.minio_endpoint or not settings.minio_access_key or not settings.minio_secret_key:
            raise StorageConfigError("MinIO is not configured.")
        if not content:
            raise ValueError("Attachment content is required.")
        if len(content) > (max_bytes or settings.attachment_max_bytes):
            raise ValueError("Attachment is too large.")
        if prefix not in {ATTACHMENT_PREFIX, TASK_IMAGE_PREFIX}:
            raise ValueError("Unsupported attachment path.")

        normalized_type = content_type.lower().split(";", 1)[0].strip()
        allowed_types = ALLOWED_IMAGE_TYPES if prefix == TASK_IMAGE_PREFIX else ALLOWED_ATTACHMENT_TYPES
        extension = allowed_types.get(normalized_type) or _extension_from_filename(filename)
        if extension == "jpeg":
            extension = "jpg"
        if extension not in set(allowed_types.values()):
            raise ValueError("Unsupported attachment type.")
        if normalized_type not in allowed_types:
            normalized_type = _content_type_from_extension(extension)

        safe_filename = _safe_filename(filename, extension)
        is_image = normalized_type in ALLOWED_IMAGE_TYPES

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
        object_name = f"{prefix}/{uuid4().hex}-{quote(safe_filename, safe='._-')}"
        client.put_object(
            settings.minio_bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=normalized_type,
        )
        return AttachmentUpload(
            object_name=object_name,
            filename=safe_filename,
            content_type=normalized_type,
            size=len(content),
            is_image=is_image,
        )

    def get_attachment(self, object_name: str) -> StoredAttachment:
        _validate_object_name(object_name, prefixes={ATTACHMENT_PREFIX, TASK_IMAGE_PREFIX})
        if not settings.minio_endpoint or not settings.minio_access_key or not settings.minio_secret_key:
            raise StorageConfigError("MinIO is not configured.")
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
        response = client.get_object(settings.minio_bucket, object_name)
        try:
            content = response.read()
            content_type = response.headers.get("Content-Type") or _content_type_from_object_name(object_name)
            filename = object_name.rsplit("/", 1)[-1]
            filename = re.sub(r"^[0-9a-f]{32}-", "", filename)
            return StoredAttachment(
                content=content,
                content_type=content_type,
                filename=filename,
                is_image=content_type.lower().split(";", 1)[0] in ALLOWED_IMAGE_TYPES,
            )
        finally:
            response.close()
            response.release_conn()


class TaskImageStorage(AttachmentStorage):
    def upload_image(self, content: bytes, content_type: str, filename: str = "") -> str:
        normalized_type = content_type.lower().split(";", 1)[0].strip()
        if normalized_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("Unsupported image type.")
        upload = self.upload_attachment(
            content,
            normalized_type,
            filename,
            prefix=TASK_IMAGE_PREFIX,
            max_bytes=settings.task_image_max_bytes,
        )
        return upload.object_name

    def get_image(self, object_name: str) -> StoredImage:
        _validate_object_name(object_name, prefixes={TASK_IMAGE_PREFIX})
        attachment = self.get_attachment(object_name)
        if not attachment.is_image:
            raise ValueError("Unsupported image type.")
        return StoredImage(content=attachment.content, content_type=attachment.content_type)


def _extension_from_filename(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].strip().lower()


def _content_type_from_object_name(object_name: str) -> str:
    return _content_type_from_extension(_extension_from_filename(object_name))


def _content_type_from_extension(extension: str) -> str:
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "pdf": "application/pdf",
        "txt": "text/plain",
        "csv": "text/csv",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "zip": "application/zip",
    }.get(extension, "application/octet-stream")


def _safe_filename(filename: str, extension: str) -> str:
    filename = unquote(filename)
    stem = filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1].strip()
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", stem).strip(".-_")
    if not stem:
        stem = f"attachment.{extension}"
    base, separator, current_extension = stem.rpartition(".")
    if separator:
        stem = f"{base.strip('.-_')}.{current_extension}"
    if "." not in stem:
        stem = f"{stem}.{extension}"
    if _extension_from_filename(stem) != extension:
        stem = f"{stem.rsplit('.', 1)[0]}.{extension}"
    return stem[:160]


def _validate_object_name(object_name: str, *, prefixes: set[str]) -> None:
    if object_name != object_name.replace("\\", "/"):
        raise ValueError("Unsupported attachment path.")
    if object_name.startswith("/") or ".." in object_name.split("/"):
        raise ValueError("Unsupported attachment path.")
    if not any(object_name.startswith(f"{prefix}/") for prefix in prefixes):
        raise ValueError("Unsupported attachment path.")
