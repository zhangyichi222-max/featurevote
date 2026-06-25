from fastapi import HTTPException, status

from app.clients.minio_storage import (
    ALLOWED_IMAGE_TYPES,
    AttachmentStorage,
    StorageConfigError,
    StoredAttachment,
    StoredImage,
    TaskImageStorage,
)
from app.models.post import UserModel
from app.schemas.post import ActionResult
from app.repositories.tasks import TasksRepository
from app.schemas.task import (
    AttachmentUploadResponse,
    TaskAssetUploadResponse,
    TaskAssigneeListResponse,
    TaskCreate,
    TaskItem,
    TaskLabelCreate,
    TaskLabelListResponse,
    TaskListResponse,
    TaskUpdate,
)


class TasksService:
    def __init__(self, repository: TasksRepository, image_storage: TaskImageStorage | None = None) -> None:
        self.repository = repository
        self.attachment_storage = image_storage or AttachmentStorage()
        self.image_storage = image_storage or TaskImageStorage()

    async def list_tasks(
        self,
        query: str = "",
        statuses: list[str] | None = None,
        assignee_id: str = "",
        labels: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TaskListResponse:
        items, total = self.repository.list_tasks(
            query=query,
            statuses=statuses,
            assignee_id=assignee_id,
            labels=labels,
            page=page,
            page_size=page_size,
        )
        return TaskListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    async def get_task(self, task_id: str) -> TaskItem:
        task = self.repository.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return task

    async def create_task(self, payload: TaskCreate, user: UserModel) -> TaskItem:
        if payload.assignee_user_id and not self.repository.user_exists(payload.assignee_user_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee not found.")
        return self.repository.create_task(payload, user)

    async def convert_post_to_task(self, post_id: str, payload: TaskCreate, user: UserModel) -> TaskItem:
        if payload.assignee_user_id and not self.repository.user_exists(payload.assignee_user_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee not found.")
        post, task = self.repository.convert_post_to_task(post_id, payload, user)
        if post is None or task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")
        return task

    async def update_task(self, task_id: str, payload: TaskUpdate, user: UserModel) -> TaskItem:
        task = self.repository.get_task_model(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        if payload.assignee_user_id and not self.repository.user_exists(payload.assignee_user_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee not found.")

        updated = self.repository.update_task(task_id, payload, user)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return updated

    async def delete_task(self, task_id: str, user: UserModel) -> ActionResult:
        deleted = self.repository.delete_task(task_id, user)
        if deleted is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return ActionResult(message="Task deleted.")

    async def list_labels(self) -> TaskLabelListResponse:
        return TaskLabelListResponse(items=self.repository.list_labels())

    async def list_assignees(self) -> TaskAssigneeListResponse:
        return TaskAssigneeListResponse(items=self.repository.list_assignees())

    async def create_label(self, payload: TaskLabelCreate) -> TaskLabelListResponse:
        self.repository.create_label(payload)
        return TaskLabelListResponse(items=self.repository.list_labels())

    async def delete_label(self, label_id: str) -> ActionResult:
        if not self.repository.delete_label(label_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found.")
        return ActionResult(message="Label deleted.")

    async def upload_image(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        public_url: str | None = None,
    ) -> TaskAssetUploadResponse:
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image content is required.")
        if content_type.lower() not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type.")
        try:
            object_name = self.image_storage.upload_image(content, content_type, filename)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except StorageConfigError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return TaskAssetUploadResponse(url=public_url or object_name)

    async def get_image(self, object_name: str) -> StoredImage:
        try:
            return self.image_storage.get_image(object_name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except StorageConfigError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - normalize storage misses/provider failures for image tags.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.") from exc

    async def upload_attachment(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        public_url: str | None = None,
    ) -> AttachmentUploadResponse:
        try:
            upload = self.attachment_storage.upload_attachment(content, content_type, filename)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except StorageConfigError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return AttachmentUploadResponse(
            url=public_url or upload.object_name,
            object_name=upload.object_name,
            filename=upload.filename,
            content_type=upload.content_type,
            size=upload.size,
            is_image=upload.is_image,
        )

    async def get_attachment(self, object_name: str) -> StoredAttachment:
        try:
            return self.attachment_storage.get_attachment(object_name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except StorageConfigError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - normalize storage misses/provider failures for links.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.") from exc
