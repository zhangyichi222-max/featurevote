from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RequirementStatus = Literal["backlog", "approved", "in_progress", "done", "rejected"]


class RequirementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    creator_name: str
    creator_open_id: str


class VoteCreate(BaseModel):
    voter_name: str
    voter_open_id: str


class CommentCreate(BaseModel):
    author_name: str = Field(default="Anonymous", max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class StatusUpdate(BaseModel):
    status: RequirementStatus


class RequirementItem(BaseModel):
    id: str
    req_id: str
    title: str
    description: str
    status: RequirementStatus
    vote_count: int
    creator_name: str
    creator_open_id: str
    created_at: datetime
    updated_at: datetime


class RequirementListResponse(BaseModel):
    items: list[RequirementItem]


class CommentItem(BaseModel):
    id: str
    requirement_id: str
    author_name: str
    body: str
    created_at: datetime


class CommentListResponse(BaseModel):
    items: list[CommentItem]


class ActionResult(BaseModel):
    success: bool = True
    message: str
