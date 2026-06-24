from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.repositories.posts import PostsRepository
from app.models.post import UserModel
from app.schemas.post import (
    ActionResult,
    DuplicateUpdate,
    ModerationUpdate,
    PostCreate,
    PostItem,
    PostListResponse,
    PostUpdate,
    TagCreate,
    TagListResponse,
    VoteCreate,
)


class PostsService:
    def __init__(self, repository: PostsRepository) -> None:
        self.repository = repository

    async def list_posts(
        self,
        query: str = "",
        tags: list[str] | None = None,
        moderation: str = "",
        view: str = "trending",
    ) -> PostListResponse:
        return PostListResponse(
            items=self.repository.list_posts(
                query=query,
                tags=tags,
                moderation=moderation,
                view=view,
            )
        )

    async def get_post(self, post_id: str) -> PostItem:
        post = self.repository.get_post(post_id)
        if post is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")
        return post

    async def create_post(self, payload: PostCreate, user: UserModel) -> PostItem:
        return self.repository.create_post(payload, user)

    async def update_post(self, post_id: str, payload: PostUpdate, user: UserModel) -> PostItem:
        _ = user
        await self.get_post(post_id)
        if payload.tags is not None:
            unknown_tags = self.repository.find_unknown_tag_names(payload.tags)
            if unknown_tags:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown tags: {', '.join(unknown_tags)}",
                )
        updated = self.repository.update_post(post_id, payload)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")
        return updated

    async def vote_post(self, post_id: str, user: UserModel) -> ActionResult:
        await self.get_post(post_id)
        try:
            self.repository.create_vote(post_id, user)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already voted for this post.",
            ) from exc
        return ActionResult(message="Vote submitted successfully.")

    async def list_tags(self) -> TagListResponse:
        return TagListResponse(items=self.repository.list_tags())

    async def create_tag(self, payload: TagCreate) -> ActionResult:
        self.repository.create_tag(payload)
        return ActionResult(message="Tag created successfully.")

    async def mark_duplicate(self, post_id: str, payload: DuplicateUpdate, actor: UserModel) -> PostItem:
        if post_id == payload.original_post_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A post cannot duplicate itself.")
        await self.get_post(post_id)
        await self.get_post(payload.original_post_id)
        return self.repository.mark_duplicate(post_id, payload, actor)

    async def moderate_post(self, post_id: str, payload: ModerationUpdate) -> PostItem:
        await self.get_post(post_id)
        return self.repository.moderate_post(post_id, payload)

    async def archive_post(self, post_id: str, actor: UserModel) -> PostItem:
        await self.get_post(post_id)
        post = self.repository.archive_post(post_id, actor)
        if post is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")
        return post
