from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RequirementModel(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    req_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_open_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now, onupdate=utc_now)

    votes: Mapped[list["VoteModel"]] = relationship(
        back_populates="requirement",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list["CommentModel"]] = relationship(
        back_populates="requirement",
        cascade="all, delete-orphan",
        order_by="CommentModel.created_at",
    )


class VoteModel(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("requirement_id", "voter_open_id", name="uq_votes_requirement_voter"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
    )
    voter_open_id: Mapped[str] = mapped_column(String(255), nullable=False)
    voter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    requirement: Mapped[RequirementModel] = relationship(back_populates="votes")


class CommentModel(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    requirement: Mapped[RequirementModel] = relationship(back_populates="comments")
