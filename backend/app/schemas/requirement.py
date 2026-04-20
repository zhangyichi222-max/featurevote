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


class ActionResult(BaseModel):
    success: bool = True
    message: str
