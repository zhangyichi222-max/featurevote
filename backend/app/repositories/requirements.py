from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.requirement import RequirementModel, VoteModel
from app.schemas.requirement import RequirementCreate, RequirementItem, VoteCreate


class RequirementsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def list_requirements(self) -> list[RequirementItem]:
        records = self.session.scalars(
            select(RequirementModel).order_by(RequirementModel.created_at.desc())
        ).all()
        return [self._to_requirement_item(record) for record in records]

    async def get_requirement_by_id(self, record_id: str) -> RequirementItem | None:
        record = self.session.get(RequirementModel, record_id)
        if record is None:
            return None
        return self._to_requirement_item(record)

    async def create_requirement(self, payload: RequirementCreate) -> dict:
        now = _utc_now()
        record = RequirementModel(
            id=uuid4().hex,
            req_id=f"REQ-{uuid4().hex[:8].upper()}",
            title=payload.title,
            description=payload.description,
            status="backlog",
            vote_count=0,
            creator_name=payload.creator_name,
            creator_open_id=payload.creator_open_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._requirement_result(record)

    async def create_vote(self, requirement_id: str, payload: VoteCreate) -> dict:
        record = VoteModel(
            id=uuid4().hex,
            requirement_id=requirement_id,
            voter_open_id=payload.voter_open_id,
            voter_name=payload.voter_name,
            created_at=_utc_now(),
        )
        self.session.add(record)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise

        self.session.refresh(record)
        return {
            "record_id": record.id,
            "fields": {
                "requirement_id": record.requirement_id,
                "voter_open_id": record.voter_open_id,
                "voter_name": record.voter_name,
                "created_at": record.created_at.isoformat(),
            },
        }

    async def has_vote(self, requirement_id: str, voter_open_id: str) -> bool:
        record = self.session.scalar(
            select(VoteModel).where(
                VoteModel.requirement_id == requirement_id,
                VoteModel.voter_open_id == voter_open_id,
            )
        )
        return record is not None

    async def update_requirement(self, record_id: str, fields: dict) -> dict:
        record = self.session.get(RequirementModel, record_id)
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = _utc_now()
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._requirement_result(record)

    def _to_requirement_item(self, record: RequirementModel) -> RequirementItem:
        return RequirementItem(
            id=record.id,
            req_id=record.req_id,
            title=record.title,
            description=record.description,
            status=record.status,
            vote_count=record.vote_count,
            creator_name=record.creator_name,
            creator_open_id=record.creator_open_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _requirement_result(self, record: RequirementModel) -> dict:
        return {
            "record_id": record.id,
            "fields": {
                "req_id": record.req_id,
                "title": record.title,
                "description": record.description,
                "status": record.status,
                "vote_count": record.vote_count,
                "creator_name": record.creator_name,
                "creator_open_id": record.creator_open_id,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            },
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
