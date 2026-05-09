from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.post import (
    CommentModel,
    NotificationTaskModel,
    PostModel,
    PostResponseModel,
    TagModel,
    TenantModel,
    UserModel,
    VoteModel,
)
from app.schemas.post import (
    CommentCreate,
    CommentItem,
    DuplicateUpdate,
    ModerationUpdate,
    PostCreate,
    PostItem,
    StatusResponseUpdate,
    TagCreate,
    TagItem,
    VoteCreate,
)

DEFAULT_TENANT_ID = "defaulttenant000000000000000000"
HOT_VOTE_THRESHOLD = 10
NOTIFICATION_MAX_ATTEMPTS = 3
NOTIFY_STATUS_VALUES = {"planned", "in_progress", "completed", "declined", "done", "rejected"}
NOTIFICATION_STATUS_LABELS = {"completed": "done", "declined": "rejected"}
RESPONSE_FALLBACK = "\u6682\u65e0"


class PostsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_seed_data(self) -> None:
        tenant = self.session.get(TenantModel, DEFAULT_TENANT_ID)
        if tenant is None:
            tenant = TenantModel(
                id=DEFAULT_TENANT_ID,
                name="FeatureVote",
                slug="featurevote",
                is_moderation_enabled=True,
                created_at=_utc_now(),
            )
            self.session.add(tenant)

        for name, color in [
            ("Feature", "#2f75d6"),
            ("Improvement", "#1f8a5b"),
            ("Bug", "#b83245"),
        ]:
            slug = _slugify(name)
            tag = self.session.scalar(
                select(TagModel).where(TagModel.tenant_id == DEFAULT_TENANT_ID, TagModel.slug == slug)
            )
            if tag is None:
                self.session.add(
                    TagModel(
                        id=uuid4().hex,
                        tenant_id=DEFAULT_TENANT_ID,
                        name=name,
                        slug=slug,
                        color=color,
                        is_public=True,
                    )
                )

        self.session.commit()

    def list_posts(
        self,
        query: str = "",
        statuses: list[str] | None = None,
        tags: list[str] | None = None,
        moderation: str = "",
        view: str = "trending",
    ) -> list[PostItem]:
        statement = self._post_select()

        if statuses:
            statement = statement.where(PostModel.status.in_(statuses))

        if query:
            term = f"%{query.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(PostModel.title).like(term),
                    func.lower(PostModel.description).like(term),
                    func.lower(PostModel.slug).like(term),
                )
            )

        if tags:
            statement = statement.join(PostModel.tags).where(TagModel.slug.in_(tags))

        if moderation == "pending":
            statement = statement.where(PostModel.is_approved.is_(False))
        elif moderation == "approved":
            statement = statement.where(PostModel.is_approved.is_(True))

        if view == "newest":
            statement = statement.order_by(PostModel.created_at.desc())
        elif view == "recent":
            statement = statement.order_by(PostModel.updated_at.desc())
        else:
            statement = statement.order_by(PostModel.updated_at.desc())

        posts = self.session.scalars(statement).unique().all()
        result = [self._to_post_item(post) for post in posts]
        if view == "trending":
            return sorted(result, key=lambda item: (item.votes_count, item.comments_count, item.updated_at), reverse=True)
        return result

    def get_post(self, post_id: str) -> PostItem | None:
        post = self.session.scalars(self._post_select().where(PostModel.id == post_id)).first()
        if post is None:
            return None
        return self._to_post_item(post)

    def list_posts_for_similarity(self) -> list[PostModel]:
        statement = (
            select(PostModel)
            .where(PostModel.archived_at.is_(None), PostModel.status != "duplicate")
            .options(selectinload(PostModel.votes))
            .order_by(PostModel.updated_at.desc())
        )
        return list(self.session.scalars(statement).unique().all())

    def get_active_post_model(self, post_id: str) -> PostModel | None:
        return self.session.scalars(self._post_select().where(PostModel.id == post_id)).first()

    def create_post(self, payload: PostCreate, user: UserModel) -> PostItem:
        number = self._next_post_number()
        title_slug = _slugify(payload.title)
        slug = self._unique_post_slug(title_slug)
        post = PostModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            user_id=user.id,
            number=number,
            title=payload.title.strip(),
            slug=slug,
            description=payload.description,
            status="open",
            is_approved=True,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        post.tags = [self.ensure_tag(tag_name) for tag_name in payload.tags]
        self.session.add(post)
        self.session.commit()
        return self.get_post(post.id)

    def create_vote(self, post_id: str, user: UserModel) -> None:
        post = self.get_active_post_model(post_id)
        vote = VoteModel(id=uuid4().hex, post_id=post_id, user_id=user.id, created_at=_utc_now())
        self.session.add(vote)
        try:
            self.session.flush()
            votes_count = int(
                self.session.scalar(select(func.count(VoteModel.id)).where(VoteModel.post_id == post_id)) or 0
            )
            if post is not None and post.hot_at is None and votes_count >= HOT_VOTE_THRESHOLD:
                post.hot_at = _utc_now()
                post.updated_at = _utc_now()
                self._enqueue_hot_notification(post, votes_count)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise

    def list_comments(self, post_id: str) -> list[CommentItem]:
        records = self.session.scalars(
            select(CommentModel)
            .options(selectinload(CommentModel.user))
            .where(CommentModel.post_id == post_id)
            .order_by(CommentModel.created_at.asc())
        ).all()
        return [self._to_comment_item(record) for record in records]

    def create_comment(self, post_id: str, payload: CommentCreate, user: UserModel) -> CommentItem:
        comment = CommentModel(
            id=uuid4().hex,
            post_id=post_id,
            user_id=user.id,
            body=payload.body,
            is_approved=True,
            created_at=_utc_now(),
        )
        self.session.add(comment)
        self.session.commit()
        self.session.refresh(comment)
        return self._to_comment_item(comment)

    def list_tags(self) -> list[TagItem]:
        tags = self.session.scalars(
            select(TagModel).where(TagModel.tenant_id == DEFAULT_TENANT_ID).order_by(TagModel.name.asc())
        ).all()
        return [self._to_tag_item(tag) for tag in tags]

    def create_tag(self, payload: TagCreate) -> TagItem:
        tag = self.ensure_tag(payload.name, color=payload.color, is_public=payload.is_public)
        self.session.commit()
        return self._to_tag_item(tag)

    def set_response(self, post_id: str, payload: StatusResponseUpdate, admin: UserModel) -> PostItem:
        post = self.get_active_post_model(post_id)
        previous_status = post.status
        post.status = payload.status
        post.updated_at = _utc_now()
        if post.response is None:
            post.response = PostResponseModel(
                id=uuid4().hex,
                post_id=post_id,
                user_id=admin.id,
                text=payload.text,
                responded_at=_utc_now(),
            )
        else:
            post.response.text = payload.text
            post.response.user_id = admin.id
            post.response.responded_at = _utc_now()
        if previous_status != payload.status and payload.status in NOTIFY_STATUS_VALUES:
            self._enqueue_status_notification(post, previous_status, payload.status, payload.text)
        self.session.add(post)
        self.session.commit()
        return self.get_post(post_id)

    def mark_duplicate(self, post_id: str, payload: DuplicateUpdate, admin: UserModel) -> PostItem:
        post = self.get_active_post_model(post_id)
        original = self.get_active_post_model(payload.original_post_id)
        post.status = "duplicate"
        post.duplicate_of_id = original.id
        post.updated_at = _utc_now()
        if post.response is None:
            post.response = PostResponseModel(
                id=uuid4().hex,
                post_id=post.id,
                user_id=admin.id,
                text=payload.text,
                responded_at=_utc_now(),
            )
        else:
            post.response.text = payload.text
            post.response.user_id = admin.id
            post.response.responded_at = _utc_now()
        self.session.add(post)
        self.session.commit()
        return self.get_post(post_id)

    def moderate_post(self, post_id: str, payload: ModerationUpdate) -> PostItem:
        post = self.get_active_post_model(post_id)
        post.is_approved = payload.is_approved
        post.updated_at = _utc_now()
        self.session.add(post)
        self.session.commit()
        return self.get_post(post_id)

    def archive_post(self, post_id: str, admin: UserModel) -> PostItem | None:
        post = self.get_active_post_model(post_id)
        if post is None:
            return None
        item = self._to_post_item(post)
        post.archived_at = _utc_now()
        post.archived_by_user_id = admin.id
        post.updated_at = _utc_now()
        self.session.add(post)
        self.session.commit()
        return item

    def ensure_user(self, external_id: str, name: str) -> UserModel:
        external_id = external_id or "anonymous"
        name = name or "Anonymous"
        user = self._get_user_by_external_id(external_id)
        if user is not None:
            if user.name != name:
                user.name = name
                self.session.add(user)
                self.session.flush()
            return user

        user = UserModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            external_id=external_id,
            name=name,
            role="visitor",
            created_at=_utc_now(),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def ensure_tag(self, name: str, color: str = "#2f75d6", is_public: bool = True) -> TagModel:
        name = name.strip()
        slug = _slugify(name)
        tag = self.session.scalar(
            select(TagModel).where(TagModel.tenant_id == DEFAULT_TENANT_ID, TagModel.slug == slug)
        )
        if tag is not None:
            return tag

        tag = TagModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            name=name,
            slug=slug,
            color=color,
            is_public=is_public,
        )
        self.session.add(tag)
        self.session.flush()
        return tag

    def _post_select(self):
        return select(PostModel).where(PostModel.archived_at.is_(None)).options(
            selectinload(PostModel.user),
            selectinload(PostModel.tags),
            selectinload(PostModel.votes),
            selectinload(PostModel.comments),
            selectinload(PostModel.response).selectinload(PostResponseModel.user),
            selectinload(PostModel.duplicate_of),
            selectinload(PostModel.linked_task),
        )

    def _next_post_number(self) -> int:
        value = self.session.scalar(
            select(func.coalesce(func.max(PostModel.number), 0)).where(PostModel.tenant_id == DEFAULT_TENANT_ID)
        )
        return int(value) + 1

    def _unique_post_slug(self, base_slug: str) -> str:
        slug = base_slug or "post"
        suffix = 2
        while self.session.scalar(select(PostModel.id).where(PostModel.tenant_id == DEFAULT_TENANT_ID, PostModel.slug == slug)):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        return slug

    def _get_user_by_external_id(self, external_id: str) -> UserModel | None:
        return self.session.scalar(
            select(UserModel).where(UserModel.tenant_id == DEFAULT_TENANT_ID, UserModel.external_id == external_id)
        )

    def _to_post_item(self, post: PostModel) -> PostItem:
        duplicate_of = None
        if post.duplicate_of is not None and post.duplicate_of.archived_at is None:
            duplicate_of = {
                "id": post.duplicate_of.id,
                "number": post.duplicate_of.number,
                "title": post.duplicate_of.title,
                "slug": post.duplicate_of.slug,
                "status": post.duplicate_of.status,
            }

        return PostItem(
            id=post.id,
            number=post.number,
            slug=post.slug,
            title=post.title,
            description=post.description,
            status=post.status,
            is_approved=post.is_approved,
            votes_count=len(post.votes),
            comments_count=len([comment for comment in post.comments if comment.is_approved]),
            has_voted=False,
            user=self._to_user_item(post.user),
            tags=[self._to_tag_item(tag) for tag in post.tags],
            response=self._to_response_item(post.response) if post.response else None,
            duplicate_of=duplicate_of,
            linked_task=self._to_linked_task_item(post.linked_task) if post.linked_task and post.linked_task.archived_at is None else None,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    def _to_comment_item(self, comment: CommentModel) -> CommentItem:
        return CommentItem(
            id=comment.id,
            post_id=comment.post_id,
            author=self._to_user_item(comment.user),
            body=comment.body,
            is_approved=comment.is_approved,
            created_at=comment.created_at,
        )

    def _to_tag_item(self, tag: TagModel) -> TagItem:
        return TagItem(id=tag.id, name=tag.name, slug=tag.slug, color=tag.color, is_public=tag.is_public)

    def _to_user_item(self, user: UserModel):
        return {"id": user.id, "name": user.name, "role": user.role}

    def _to_response_item(self, response: PostResponseModel):
        return {"text": response.text, "responded_at": response.responded_at, "user": self._to_user_item(response.user)}

    def _to_linked_task_item(self, task):
        return {"id": task.id, "number": task.number, "title": task.title, "status": task.status}

    def _enqueue_status_notification(
        self,
        post: PostModel,
        previous_status: str,
        new_status: str,
        response_text: str,
    ) -> None:
        message = "\n".join(
            [
                "需求状态已更新",
                f"标题：{post.title}",
                f"新状态：{NOTIFICATION_STATUS_LABELS.get(new_status, new_status)}",
                f"管理员回复：{response_text.strip() or RESPONSE_FALLBACK}",
            ]
        )
        self._enqueue_notification(
            post=post,
            event_type="status_changed",
            dedupe_key=f"status:{previous_status}:{new_status}",
            message=message,
        )

    def _enqueue_hot_notification(self, post: PostModel, votes_count: int) -> None:
        message = "\n".join(
            [
                "需求已变热门",
                f"标题：{post.title}",
                f"当前票数：{votes_count}",
                f"热门阈值：{HOT_VOTE_THRESHOLD}",
            ]
        )
        self._enqueue_notification(
            post=post,
            event_type="hot",
            dedupe_key=f"hot:{HOT_VOTE_THRESHOLD}",
            message=message,
        )

    def _enqueue_notification(self, post: PostModel, event_type: str, dedupe_key: str, message: str) -> None:
        task = NotificationTaskModel(
            id=uuid4().hex,
            tenant_id=post.tenant_id,
            post_id=post.id,
            user_id=post.user_id,
            recipient_open_id=post.user.feishu_open_id if post.user else None,
            event_type=event_type,
            dedupe_key=dedupe_key,
            message=message,
            status="pending",
            attempts=0,
            max_attempts=NOTIFICATION_MAX_ATTEMPTS,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        nested = self.session.begin_nested()
        try:
            self.session.add(task)
            self.session.flush()
            nested.commit()
        except IntegrityError:
            nested.rollback()


def seed_default_data(session: Session) -> None:
    PostsRepository(session).ensure_seed_data()


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "item"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
