from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


PostStatus = Literal["open", "planned", "in_progress", "completed", "declined", "duplicate"]


class UserItem(BaseModel):
    id: str
    name: str


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
    total: int
    page: int
    page_size: int
    total_pages: int


class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters.")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Description must not be blank.")
        return value


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    tags: list[str] | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is not None and len(value.strip()) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters.")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Description must not be blank.")
        return value


class VoteCreate(BaseModel):
    pass


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#2f75d6", max_length=24)
    is_public: bool = True


class TagListResponse(BaseModel):
    items: list[TagItem]


class DuplicateUpdate(BaseModel):
    original_post_id: str
    text: str = Field(default="This suggestion duplicates another post.", max_length=5000)


class ModerationUpdate(BaseModel):
    is_approved: bool


class ActionResult(BaseModel):
    success: bool = True
    message: str
