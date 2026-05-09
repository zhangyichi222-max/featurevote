from fastapi import HTTPException, status

from app.clients.minio_storage import ALLOWED_IMAGE_TYPES, StorageConfigError, StoredImage, TaskImageStorage
from app.models.post import UserModel
from app.repositories.tasks import TasksRepository
from app.schemas.task import (
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
        self.image_storage = image_storage or TaskImageStorage()

    async def list_tasks(
        self,
        query: str = "",
        statuses: list[str] | None = None,
        assignee_id: str = "",
        labels: list[str] | None = None,
    ) -> TaskListResponse:
        return TaskListResponse(
            items=self.repository.list_tasks(query=query, statuses=statuses, assignee_id=assignee_id, labels=labels)
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

    async def update_task(self, task_id: str, payload: TaskUpdate, user: UserModel) -> TaskItem:
        task = self.repository.get_task_model(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        allow_admin_fields = user.role == "admin"
        if not allow_admin_fields and task.assignee_user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins or assignees can update tasks.")
        if not allow_admin_fields and (payload.title is not None or "assignee_user_id" in payload.model_fields_set or payload.labels is not None):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignees can only update status and description.")
        if allow_admin_fields and payload.assignee_user_id and not self.repository.user_exists(payload.assignee_user_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee not found.")

        updated = self.repository.update_task(task_id, payload, user, allow_admin_fields=allow_admin_fields)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return updated

    async def list_labels(self) -> TaskLabelListResponse:
        return TaskLabelListResponse(items=self.repository.list_labels())

    async def create_label(self, payload: TaskLabelCreate) -> TaskLabelListResponse:
        self.repository.create_label(payload)
        return TaskLabelListResponse(items=self.repository.list_labels())

    async def list_assignees(self) -> TaskAssigneeListResponse:
        return TaskAssigneeListResponse(items=self.repository.list_assignees())

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
