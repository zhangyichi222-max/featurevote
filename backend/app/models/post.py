from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_moderation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    users: Mapped[list["UserModel"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    posts: Mapped[list["PostModel"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    tags: Mapped[list["TagModel"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_users_tenant_external"),
        UniqueConstraint("tenant_id", "feishu_open_id", name="uq_users_tenant_feishu_open"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    feishu_open_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feishu_union_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    department_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    group_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now, onupdate=utc_now)

    tenant: Mapped[TenantModel] = relationship(back_populates="users")
    posts: Mapped[list["PostModel"]] = relationship(back_populates="user", foreign_keys="PostModel.user_id")


class PostTagModel(Base):
    __tablename__ = "post_tags"
    __table_args__ = (UniqueConstraint("post_id", "tag_id", name="uq_post_tags_post_tag"),)

    post_id: Mapped[str] = mapped_column(String(32), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(32), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class TagModel(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_tags_tenant_slug"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(24), nullable=False, default="#2f75d6")
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped[TenantModel] = relationship(back_populates="tags")
    posts: Mapped[list["PostModel"]] = relationship(secondary="post_tags", back_populates="tags")
    tasks: Mapped[list["TaskModel"]] = relationship(secondary="task_label_links", back_populates="labels")


class PostModel(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_posts_tenant_number"),
        UniqueConstraint("tenant_id", "slug", name="uq_posts_tenant_slug"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("posts.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    archived_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now, onupdate=utc_now)

    tenant: Mapped[TenantModel] = relationship(back_populates="posts")
    user: Mapped[UserModel] = relationship(back_populates="posts", foreign_keys=[user_id])
    tags: Mapped[list[TagModel]] = relationship(secondary="post_tags", back_populates="posts")
    votes: Mapped[list["VoteModel"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    response: Mapped["PostResponseModel | None"] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        uselist=False,
    )
    linked_task: Mapped["TaskModel | None"] = relationship(back_populates="source_post", uselist=False)
    duplicate_of: Mapped["PostModel | None"] = relationship(remote_side=[id])
    archived_by: Mapped[UserModel | None] = relationship(foreign_keys=[archived_by_user_id])


class VoteModel(Base):
    __tablename__ = "post_votes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_votes_post_user"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(32), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    post: Mapped[PostModel] = relationship(back_populates="votes")
    user: Mapped[UserModel] = relationship()


class PostResponseModel(Base):
    __tablename__ = "post_responses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    post_id: Mapped[str] = mapped_column(String(32), ForeignKey("posts.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    responded_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    post: Mapped[PostModel] = relationship(back_populates="response")
    user: Mapped[UserModel] = relationship()


class TaskLabelLinkModel(Base):
    __tablename__ = "task_label_links"
    __table_args__ = (UniqueConstraint("task_id", "label_id", name="uq_task_label_links_task_label"),)

    task_id: Mapped[str] = mapped_column(String(32), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    label_id: Mapped[str] = mapped_column(String(32), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_tasks_tenant_number"),
        UniqueConstraint("tenant_id", "source_post_id", name="uq_tasks_tenant_source_post"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="todo")
    source_post_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    assignee_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now, onupdate=utc_now)

    tenant: Mapped[TenantModel] = relationship()
    source_post: Mapped[PostModel | None] = relationship(back_populates="linked_task")
    assignee: Mapped[UserModel | None] = relationship(foreign_keys=[assignee_user_id])
    created_by: Mapped[UserModel] = relationship(foreign_keys=[created_by_user_id])
    updated_by: Mapped[UserModel | None] = relationship(foreign_keys=[updated_by_user_id])
    labels: Mapped[list[TagModel]] = relationship(secondary="task_label_links", back_populates="tasks")


class NotificationTaskModel(Base):
    __tablename__ = "notification_tasks"
    __table_args__ = (
        UniqueConstraint("post_id", "event_type", "dedupe_key", name="uq_notification_tasks_dedupe"),
        UniqueConstraint("task_id", "event_type", "dedupe_key", name="uq_notification_tasks_task_dedupe"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    recipient_open_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now, onupdate=utc_now)

    tenant: Mapped[TenantModel] = relationship()
    post: Mapped[PostModel | None] = relationship()
    task: Mapped[TaskModel | None] = relationship()
    user: Mapped[UserModel] = relationship()


class FeishuImportedMessageModel(Base):
    __tablename__ = "feishu_imported_messages"
    __table_args__ = (UniqueConstraint("message_id", name="uq_feishu_imported_messages_message"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_open_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now, onupdate=utc_now)

    tenant: Mapped[TenantModel] = relationship()
    post: Mapped[PostModel | None] = relationship()
