from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.post import UserItem


TaskStatus = Literal["todo", "in_progress", "blocked", "done", "canceled"]


class TaskSourcePostItem(BaseModel):
    id: str
    number: int
    title: str
    status: str


class TaskLabelItem(BaseModel):
    id: str
    name: str
    slug: str
    color: str


class TaskItem(BaseModel):
    id: str
    number: int
    title: str
    description_markdown: str
    status: TaskStatus
    assignee: UserItem | None
    created_by: UserItem
    updated_by: UserItem | None = None
    source_post: TaskSourcePostItem | None = None
    labels: list[TaskLabelItem]
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskItem]


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description_markdown: str = Field(default="", max_length=20000)
    status: TaskStatus = "todo"
    assignee_user_id: str | None = None
    labels: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description_markdown: str | None = Field(default=None, max_length=20000)
    status: TaskStatus | None = None
    assignee_user_id: str | None = None
    labels: list[str] | None = None


class TaskLabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#2f75d6", max_length=24)


class TaskLabelListResponse(BaseModel):
    items: list[TaskLabelItem]


class TaskAssetUploadResponse(BaseModel):
    url: str


class AttachmentUploadResponse(BaseModel):
    url: str
    object_name: str
    filename: str
    content_type: str
    size: int
    is_image: bool


class TaskAssigneeListResponse(BaseModel):
    items: list[UserItem]


class FeishuMessageEvidence(BaseModel):
    conversation_id: str = Field(max_length=120)
    conversation_title: str = Field(default="", max_length=240)
    message_id: str = Field(max_length=120)
    sender_name: str = Field(default="", max_length=120)
    created_at: str = Field(default="", max_length=80)
    content: str = Field(max_length=1200)


class FeishuTaskCandidate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=3, max_length=160)
    description_markdown: str = Field(default="", max_length=20000)
    evidence: list[FeishuMessageEvidence] = Field(default_factory=list)
    duplicate_hints: list[TaskSourcePostItem] = Field(default_factory=list)


class FeishuTaskImportPreviewResponse(BaseModel):
    candidates: list[FeishuTaskCandidate]
    conversations_count: int
    messages_count: int
    skipped_messages_count: int


class FeishuTaskImportCreateRequest(BaseModel):
    candidates: list[FeishuTaskCandidate] = Field(min_length=1, max_length=50)


class FeishuTaskImportCreateResponse(BaseModel):
    items: list[TaskItem]
