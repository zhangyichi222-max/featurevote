from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PostStatus = Literal["open", "planned", "in_progress", "completed", "declined", "duplicate"]
UserRole = Literal["visitor", "admin"]


class UserItem(BaseModel):
    id: str
    name: str
    role: UserRole


class TagItem(BaseModel):
    id: str
    name: str
    slug: str
    color: str
    is_public: bool


class PostResponseItem(BaseModel):
    text: str
    responded_at: datetime
    user: UserItem


class OriginalPostItem(BaseModel):
    id: str
    number: int
    title: str
    slug: str
    status: PostStatus


class LinkedTaskItem(BaseModel):
    id: str
    number: int
    title: str
    status: str


class PostItem(BaseModel):
    id: str
    number: int
    slug: str
    title: str
    description: str
    status: PostStatus
    is_approved: bool
    votes_count: int
    comments_count: int
    has_voted: bool
    user: UserItem
    tags: list[TagItem]
    response: PostResponseItem | None = None
    duplicate_of: OriginalPostItem | None = None
    linked_task: LinkedTaskItem | None = None
    created_at: datetime
    updated_at: datetime


class PostListResponse(BaseModel):
    items: list[PostItem]


class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list)


class VoteCreate(BaseModel):
    pass


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentItem(BaseModel):
    id: str
    post_id: str
    author: UserItem
    body: str
    is_approved: bool
    created_at: datetime


class CommentListResponse(BaseModel):
    items: list[CommentItem]


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#2f75d6", max_length=24)
    is_public: bool = True


class TagListResponse(BaseModel):
    items: list[TagItem]


class StatusResponseUpdate(BaseModel):
    status: PostStatus
    text: str = Field(min_length=1, max_length=5000)


class DuplicateUpdate(BaseModel):
    original_post_id: str
    text: str = Field(default="This suggestion duplicates another post.", max_length=5000)


class ModerationUpdate(BaseModel):
    is_approved: bool


class ActionResult(BaseModel):
    success: bool = True
    message: str
