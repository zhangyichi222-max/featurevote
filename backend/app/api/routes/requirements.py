from fastapi import APIRouter, Depends

from app.api.deps import get_requirements_service
from app.schemas.requirement import (
    ActionResult,
    CommentCreate,
    CommentListResponse,
    RequirementCreate,
    RequirementListResponse,
    StatusUpdate,
    VoteCreate,
)
from app.services.requirements import RequirementsService


router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.get("", response_model=RequirementListResponse)
async def list_requirements(
    service: RequirementsService = Depends(get_requirements_service),
) -> RequirementListResponse:
    return await service.list_requirements()


@router.post("", response_model=ActionResult)
async def create_requirement(
    payload: RequirementCreate,
    service: RequirementsService = Depends(get_requirements_service),
) -> ActionResult:
    await service.create_requirement(payload)
    return ActionResult(message="Requirement created successfully.")


@router.get("/{requirement_id}/comments", response_model=CommentListResponse)
async def list_comments(
    requirement_id: str,
    service: RequirementsService = Depends(get_requirements_service),
) -> CommentListResponse:
    return await service.list_comments(requirement_id)


@router.post("/{requirement_id}/comments", response_model=ActionResult)
async def create_comment(
    requirement_id: str,
    payload: CommentCreate,
    service: RequirementsService = Depends(get_requirements_service),
) -> ActionResult:
    await service.create_comment(requirement_id, payload)
    return ActionResult(message="Comment added successfully.")


@router.post("/{requirement_id}/vote", response_model=ActionResult)
async def vote_requirement(
    requirement_id: str,
    payload: VoteCreate,
    service: RequirementsService = Depends(get_requirements_service),
) -> ActionResult:
    await service.vote_requirement(requirement_id, payload)
    return ActionResult(message="Vote submitted successfully.")


@router.post("/{requirement_id}/status", response_model=ActionResult)
async def update_requirement_status(
    requirement_id: str,
    payload: StatusUpdate,
    service: RequirementsService = Depends(get_requirements_service),
) -> ActionResult:
    await service.update_status(requirement_id, payload)
    return ActionResult(message="Requirement status updated successfully.")
