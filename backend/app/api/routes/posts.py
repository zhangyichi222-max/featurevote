from fastapi import APIRouter, Depends, Query

from app.api.deps import get_posts_service, get_tasks_service, require_admin_user, require_current_user, require_mutating_origin
from app.models.post import UserModel
from app.schemas.post import (
    ActionResult,
    DuplicateUpdate,
    ModerationUpdate,
    PostCreate,
    PostItem,
    PostListResponse,
    StatusResponseUpdate,
    TagCreate,
    TagListResponse,
    VoteCreate,
)
from app.services.posts import PostsService
from app.schemas.task import TaskCreate
from app.services.tasks import TasksService


router = APIRouter(prefix="/posts", tags=["posts"])
tags_router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=PostListResponse)
async def list_posts(
    query: str = "",
    statuses: list[str] | None = Query(default=None),
    tags: list[str] | None = Query(default=None),
    moderation: str = "",
    view: str = "trending",
    service: PostsService = Depends(get_posts_service),
) -> PostListResponse:
    return await service.list_posts(query=query, statuses=statuses, tags=tags, moderation=moderation, view=view)


@router.post("", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def create_post(
    payload: PostCreate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> PostItem:
    return await service.create_post(payload, user)


@router.get("/{post_id}", response_model=PostItem)
async def get_post(post_id: str, service: PostsService = Depends(get_posts_service)) -> PostItem:
    return await service.get_post(post_id)


@router.post("/{post_id}/vote", response_model=ActionResult, dependencies=[Depends(require_mutating_origin)])
async def vote_post(
    post_id: str,
    payload: VoteCreate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> ActionResult:
    return await service.vote_post(post_id, user)


@router.post("/{post_id}/response", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def set_response(
    post_id: str,
    payload: StatusResponseUpdate,
    service: PostsService = Depends(get_posts_service),
    admin: UserModel = Depends(require_admin_user),
) -> PostItem:
    return await service.set_response(post_id, payload, admin)


@router.post("/{post_id}/convert-to-task", dependencies=[Depends(require_mutating_origin)])
async def convert_post_to_task(
    post_id: str,
    payload: TaskCreate,
    posts_service: PostsService = Depends(get_posts_service),
    tasks_service: TasksService = Depends(get_tasks_service),
    admin: UserModel = Depends(require_admin_user),
) -> dict[str, object]:
    task = await tasks_service.convert_post_to_task(post_id, payload, admin)
    post = await posts_service.get_post(post_id)
    return {"post": post, "task": task}


@router.post("/{post_id}/duplicate", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def mark_duplicate(
    post_id: str,
    payload: DuplicateUpdate,
    service: PostsService = Depends(get_posts_service),
    admin: UserModel = Depends(require_admin_user),
) -> PostItem:
    return await service.mark_duplicate(post_id, payload, admin)


@router.post("/{post_id}/moderation", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def moderate_post(
    post_id: str,
    payload: ModerationUpdate,
    service: PostsService = Depends(get_posts_service),
    admin: UserModel = Depends(require_admin_user),
) -> PostItem:
    _ = admin
    return await service.moderate_post(post_id, payload)


@router.post("/{post_id}/archive", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def archive_post(
    post_id: str,
    service: PostsService = Depends(get_posts_service),
    admin: UserModel = Depends(require_admin_user),
) -> PostItem:
    return await service.archive_post(post_id, admin)


@tags_router.get("", response_model=TagListResponse)
async def list_tags(service: PostsService = Depends(get_posts_service)) -> TagListResponse:
    return await service.list_tags()


@tags_router.post("", response_model=ActionResult, dependencies=[Depends(require_mutating_origin)])
async def create_tag(
    payload: TagCreate,
    service: PostsService = Depends(get_posts_service),
    admin: UserModel = Depends(require_admin_user),
) -> ActionResult:
    _ = admin
    return await service.create_tag(payload)
