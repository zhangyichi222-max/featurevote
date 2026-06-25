from fastapi import APIRouter, Depends, Query

from app.api.deps import get_posts_service, get_tasks_service, require_current_user, require_mutating_origin
from app.models.post import UserModel
from app.schemas.post import (
    ActionResult,
    DuplicateUpdate,
    ModerationUpdate,
    PostCreate,
    PostItem,
    PostListResponse,
    PostSourcesResponse,
    PostUpdate,
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
    tags: list[str] | None = Query(default=None),
    moderation: str = "",
    view: str = "trending",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: PostsService = Depends(get_posts_service),
) -> PostListResponse:
    return await service.list_posts(
        query=query,
        tags=tags,
        moderation=moderation,
        view=view,
        page=page,
        page_size=page_size,
    )


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


@router.get("/{post_id}/sources", response_model=PostSourcesResponse)
async def get_post_sources(
    post_id: str,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> PostSourcesResponse:
    _ = user
    return await service.get_post_sources(post_id)


@router.patch("/{post_id}", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def update_post(
    post_id: str,
    payload: PostUpdate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> PostItem:
    return await service.update_post(post_id, payload, user)


@router.post("/{post_id}/vote", response_model=ActionResult, dependencies=[Depends(require_mutating_origin)])
async def vote_post(
    post_id: str,
    payload: VoteCreate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> ActionResult:
    return await service.vote_post(post_id, user)


@router.post("/{post_id}/convert-to-task", dependencies=[Depends(require_mutating_origin)])
async def convert_post_to_task(
    post_id: str,
    payload: TaskCreate,
    tasks_service: TasksService = Depends(get_tasks_service),
    user: UserModel = Depends(require_current_user),
) -> dict[str, object]:
    task = await tasks_service.convert_post_to_task(post_id, payload, user)
    return {"task": task}


@router.post("/{post_id}/duplicate", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def mark_duplicate(
    post_id: str,
    payload: DuplicateUpdate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> PostItem:
    return await service.mark_duplicate(post_id, payload, user)


@router.post("/{post_id}/moderation", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def moderate_post(
    post_id: str,
    payload: ModerationUpdate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> PostItem:
    _ = user
    return await service.moderate_post(post_id, payload)


@router.post("/{post_id}/archive", response_model=PostItem, dependencies=[Depends(require_mutating_origin)])
async def archive_post(
    post_id: str,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> PostItem:
    return await service.archive_post(post_id, user)


@tags_router.get("", response_model=TagListResponse)
async def list_tags(service: PostsService = Depends(get_posts_service)) -> TagListResponse:
    return await service.list_tags()


@tags_router.post("", response_model=ActionResult, dependencies=[Depends(require_mutating_origin)])
async def create_tag(
    payload: TagCreate,
    service: PostsService = Depends(get_posts_service),
    user: UserModel = Depends(require_current_user),
) -> ActionResult:
    _ = user
    return await service.create_tag(payload)
