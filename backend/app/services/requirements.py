from fastapi import HTTPException, status

from app.repositories.requirements import RequirementsRepository
from app.schemas.requirement import RequirementCreate, RequirementListResponse, StatusUpdate, VoteCreate


class RequirementsService:
    def __init__(self, repository: RequirementsRepository) -> None:
        self.repository = repository

    async def list_requirements(self) -> RequirementListResponse:
        items = await self.repository.list_requirements()
        return RequirementListResponse(items=items)

    async def create_requirement(self, payload: RequirementCreate) -> dict:
        return await self.repository.create_requirement(payload)

    async def vote_requirement(self, requirement_id: str, payload: VoteCreate) -> dict:
        votes = await self.repository.list_votes()
        for vote in votes:
            fields = vote.get("fields", {})
            if (
                fields.get("requirement_id") == requirement_id
                and fields.get("voter_open_id") == payload.voter_open_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You have already voted for this requirement.",
                )

        requirements = await self.repository.list_requirements()
        target = next((item for item in requirements if item.id == requirement_id), None)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found.")

        await self.repository.create_vote(requirement_id, payload)
        return await self.repository.update_requirement(
            requirement_id,
            {"vote_count": target.vote_count + 1},
        )

    async def update_status(self, requirement_id: str, payload: StatusUpdate) -> dict:
        requirements = await self.repository.list_requirements()
        target = next((item for item in requirements if item.id == requirement_id), None)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found.")

        return await self.repository.update_requirement(
            requirement_id,
            {"status": payload.status},
        )
