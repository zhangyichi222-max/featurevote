from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import get_tasks_service, require_admin_user, require_current_user, require_mutating_origin
from app.models.post import UserModel
from app.schemas.post import ActionResult
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
from app.services.tasks import TasksService


router = APIRouter(prefix="/tasks", tags=["tasks"])
labels_router = APIRouter(prefix="/task-labels", tags=["task-labels"])
assets_router = APIRouter(prefix="/task-assets", tags=["task-assets"])


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    query: str = "",
    statuses: list[str] | None = Query(default=None),
    assignee_id: str = "",
    labels: list[str] | None = Query(default=None),
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> TaskListResponse:
    _ = user
    return await service.list_tasks(query=query, statuses=statuses, assignee_id=assignee_id, labels=labels)


@router.post("", response_model=TaskItem, dependencies=[Depends(require_mutating_origin)])
async def create_task(
    payload: TaskCreate,
    service: TasksService = Depends(get_tasks_service),
    admin: UserModel = Depends(require_admin_user),
) -> TaskItem:
    return await service.create_task(payload, admin)


@router.get("/assignees", response_model=TaskAssigneeListResponse)
async def list_assignees(
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> TaskAssigneeListResponse:
    _ = user
    return await service.list_assignees()


@router.get("/{task_id}", response_model=TaskItem)
async def get_task(
    task_id: str,
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> TaskItem:
    _ = user
    return await service.get_task(task_id)


@router.patch("/{task_id}", response_model=TaskItem, dependencies=[Depends(require_mutating_origin)])
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> TaskItem:
    return await service.update_task(task_id, payload, user)


@router.delete("/{task_id}", response_model=ActionResult, dependencies=[Depends(require_mutating_origin)])
async def delete_task(
    task_id: str,
    service: TasksService = Depends(get_tasks_service),
    admin: UserModel = Depends(require_admin_user),
) -> ActionResult:
    return await service.delete_task(task_id, admin)


@labels_router.get("", response_model=TaskLabelListResponse)
async def list_task_labels(
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> TaskLabelListResponse:
    _ = user
    return await service.list_labels()


@labels_router.post("", response_model=TaskLabelListResponse, dependencies=[Depends(require_mutating_origin)])
async def create_task_label(
    payload: TaskLabelCreate,
    service: TasksService = Depends(get_tasks_service),
    admin: UserModel = Depends(require_admin_user),
) -> TaskLabelListResponse:
    _ = admin
    return await service.create_label(payload)


@assets_router.post("/images", response_model=TaskAssetUploadResponse, dependencies=[Depends(require_mutating_origin)])
async def upload_task_image(
    request: Request,
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> TaskAssetUploadResponse:
    _ = user
    content_type = request.headers.get("content-type", "")
    filename = request.headers.get("x-file-name", "")
    content = await request.body()
    response = await service.upload_image(content, content_type, filename)
    response.url = str(request.url_for("get_task_image", object_name=response.url))
    return response


@assets_router.get("/images/{object_name:path}", name="get_task_image")
async def get_task_image(
    object_name: str,
    service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> Response:
    _ = user
    image = await service.get_image(object_name)
    return Response(
        content=image.content,
        media_type=image.content_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )
