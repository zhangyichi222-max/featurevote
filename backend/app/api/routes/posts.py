from fastapi import APIRouter, Depends, Query

from app.api.deps import get_posts_service
from app.schemas.post import (
    ActionResult,
    CommentCreate,
    CommentListResponse,
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


@router.post("", response_model=PostItem)
async def create_post(payload: PostCreate, service: PostsService = Depends(get_posts_service)) -> PostItem:
    return await service.create_post(payload)


@router.get("/{post_id}", response_model=PostItem)
async def get_post(post_id: str, service: PostsService = Depends(get_posts_service)) -> PostItem:
    return await service.get_post(post_id)


@router.post("/{post_id}/vote", response_model=ActionResult)
async def vote_post(
    post_id: str,
    payload: VoteCreate,
    service: PostsService = Depends(get_posts_service),
) -> ActionResult:
    return await service.vote_post(post_id, payload)


@router.get("/{post_id}/comments", response_model=CommentListResponse)
async def list_comments(post_id: str, service: PostsService = Depends(get_posts_service)) -> CommentListResponse:
    return await service.list_comments(post_id)


@router.post("/{post_id}/comments", response_model=ActionResult)
async def create_comment(
    post_id: str,
    payload: CommentCreate,
    service: PostsService = Depends(get_posts_service),
) -> ActionResult:
    return await service.create_comment(post_id, payload)


@router.post("/{post_id}/response", response_model=PostItem)
async def set_response(
    post_id: str,
    payload: StatusResponseUpdate,
    service: PostsService = Depends(get_posts_service),
) -> PostItem:
    return await service.set_response(post_id, payload)


@router.post("/{post_id}/duplicate", response_model=PostItem)
async def mark_duplicate(
    post_id: str,
    payload: DuplicateUpdate,
    service: PostsService = Depends(get_posts_service),
) -> PostItem:
    return await service.mark_duplicate(post_id, payload)


@router.post("/{post_id}/moderation", response_model=PostItem)
async def moderate_post(
    post_id: str,
    payload: ModerationUpdate,
    service: PostsService = Depends(get_posts_service),
) -> PostItem:
    return await service.moderate_post(post_id, payload)


@tags_router.get("", response_model=TagListResponse)
async def list_tags(service: PostsService = Depends(get_posts_service)) -> TagListResponse:
    return await service.list_tags()


@tags_router.post("", response_model=ActionResult)
async def create_tag(payload: TagCreate, service: PostsService = Depends(get_posts_service)) -> ActionResult:
    return await service.create_tag(payload)
