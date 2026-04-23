from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.repositories.requirements import RequirementsRepository
from app.schemas.requirement import (
    CommentCreate,
    CommentListResponse,
    RequirementCreate,
    RequirementListResponse,
    StatusUpdate,
    VoteCreate,
)


class RequirementsService:
    def __init__(self, repository: RequirementsRepository) -> None:
        self.repository = repository

    async def list_requirements(self) -> RequirementListResponse:
        items = await self.repository.list_requirements()
        return RequirementListResponse(items=items)

    async def create_requirement(self, payload: RequirementCreate) -> dict:
        return await self.repository.create_requirement(payload)

    async def list_comments(self, requirement_id: str) -> CommentListResponse:
        target = await self.repository.get_requirement_by_id(requirement_id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found.")

        items = await self.repository.list_comments(requirement_id)
        return CommentListResponse(items=items)

    async def create_comment(self, requirement_id: str, payload: CommentCreate) -> dict:
        target = await self.repository.get_requirement_by_id(requirement_id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found.")

        return await self.repository.create_comment(requirement_id, payload)

    async def vote_requirement(self, requirement_id: str, payload: VoteCreate) -> dict:
        if await self.repository.has_vote(requirement_id, payload.voter_open_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already voted for this requirement.",
            )

        target = await self.repository.get_requirement_by_id(requirement_id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found.")

        try:
            await self.repository.create_vote(requirement_id, payload)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already voted for this requirement.",
            ) from exc

        return await self.repository.update_requirement(
            requirement_id,
            {"vote_count": target.vote_count + 1},
        )

    async def update_status(self, requirement_id: str, payload: StatusUpdate) -> dict:
        target = await self.repository.get_requirement_by_id(requirement_id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found.")

        return await self.repository.update_requirement(
            requirement_id,
            {"status": payload.status},
        )
