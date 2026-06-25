from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.post import (
    FeishuImportedMessageModel,
    PostEmbeddingIndexModel,
    PostModel,
    PostResponseModel,
    TagModel,
    TenantModel,
    UserModel,
    VoteModel,
)
from app.schemas.post import (
    DuplicateUpdate,
    ModerationUpdate,
    PostCreate,
    PostItem,
    PostSourceGroupItem,
    PostSourceMessageItem,
    PostSourcesResponse,
    PostUpdate,
    TagCreate,
    TagItem,
    VoteCreate,
)

DEFAULT_TENANT_ID = "defaulttenant000000000000000000"
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
        tags: list[str] | None = None,
        moderation: str = "",
        view: str = "trending",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PostItem], int]:
        statement = self._post_select()
        count_statement = select(func.count(PostModel.id)).where(PostModel.archived_at.is_(None))

        if query:
            cleaned_query = query.strip().lower()
            term = f"%{cleaned_query}%"
            query_conditions = [
                func.lower(PostModel.title).like(term),
                func.lower(PostModel.description).like(term),
                func.lower(PostModel.slug).like(term),
            ]
            if cleaned_query.startswith("post-") and cleaned_query[5:].isdigit():
                query_conditions.append(PostModel.number == int(cleaned_query[5:]))
            query_filter = or_(*query_conditions)
            statement = statement.where(query_filter)
            count_statement = count_statement.where(query_filter)

        if tags:
            tag_filter = PostModel.tags.any(TagModel.slug.in_(tags))
            statement = statement.where(tag_filter)
            count_statement = count_statement.where(tag_filter)

        if moderation == "pending":
            statement = statement.where(PostModel.is_approved.is_(False))
            count_statement = count_statement.where(PostModel.is_approved.is_(False))
        elif moderation == "approved":
            statement = statement.where(PostModel.is_approved.is_(True))
            count_statement = count_statement.where(PostModel.is_approved.is_(True))

        vote_count = (
            select(func.count(VoteModel.id))
            .where(VoteModel.post_id == PostModel.id)
            .correlate(PostModel)
            .scalar_subquery()
        )
        if view == "newest":
            statement = statement.order_by(PostModel.created_at.desc(), PostModel.number.desc())
        elif view == "recent":
            statement = statement.order_by(PostModel.updated_at.desc(), PostModel.number.desc())
        else:
            statement = statement.order_by(vote_count.desc(), PostModel.updated_at.desc(), PostModel.number.desc())

        total = int(self.session.scalar(count_statement) or 0)
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        posts = self.session.scalars(statement).unique().all()
        return [self._to_post_item(post) for post in posts], total

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

    def get_post_models_by_ids(self, post_ids: list[str]) -> list[PostModel]:
        if not post_ids:
            return []
        records = self.session.scalars(
            select(PostModel)
            .where(
                PostModel.id.in_(post_ids),
                PostModel.archived_at.is_(None),
                PostModel.status != "duplicate",
            )
            .options(selectinload(PostModel.votes))
        ).unique().all()
        by_id = {record.id: record for record in records}
        return [by_id[post_id] for post_id in post_ids if post_id in by_id]

    def list_active_post_models(self) -> list[PostModel]:
        return list(
            self.session.scalars(
                select(PostModel)
                .where(PostModel.archived_at.is_(None), PostModel.status != "duplicate")
                .order_by(PostModel.number.asc())
            ).all()
        )

    def save_embedding_index_state(
        self,
        post_id: str,
        *,
        model: str,
        content_hash: str,
        status: str,
        error: str | None = None,
        indexed_at: datetime | None = None,
    ) -> None:
        record = self.session.scalar(
            select(PostEmbeddingIndexModel).where(PostEmbeddingIndexModel.post_id == post_id)
        )
        now = _utc_now()
        if record is None:
            record = PostEmbeddingIndexModel(
                id=uuid4().hex,
                tenant_id=DEFAULT_TENANT_ID,
                post_id=post_id,
                model=model,
                content_hash=content_hash,
                status=status,
                created_at=now,
                updated_at=now,
            )
        record.model = model
        record.content_hash = content_hash
        record.status = status
        record.last_error = error[:2000] if error else None
        record.indexed_at = indexed_at
        record.updated_at = now
        self.session.add(record)
        self.session.commit()

    def mark_embedding_index_removed(self, post_id: str, *, error: str | None = None) -> None:
        record = self.session.scalar(
            select(PostEmbeddingIndexModel).where(PostEmbeddingIndexModel.post_id == post_id)
        )
        if record is None:
            return
        record.status = "remove_failed" if error else "removed"
        record.last_error = error[:2000] if error else None
        record.updated_at = _utc_now()
        self.session.add(record)
        self.session.commit()

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
        vote = VoteModel(id=uuid4().hex, post_id=post_id, user_id=user.id, created_at=_utc_now())
        self.session.add(vote)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise

    def update_post(self, post_id: str, payload: PostUpdate) -> PostItem | None:
        post = self.get_active_post_model(post_id)
        if post is None:
            return None
        if payload.title is not None:
            post.title = payload.title.strip()
        if payload.description is not None:
            post.description = payload.description
        if payload.tags is not None:
            post.tags = self._get_tags_by_names(payload.tags)
        post.updated_at = _utc_now()
        self.session.add(post)
        self.session.commit()
        return self.get_post(post_id)

    def find_unknown_tag_names(self, names: list[str]) -> list[str]:
        normalized_names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        if not normalized_names:
            return []
        existing_names = set(
            self.session.scalars(
                select(TagModel.name).where(
                    TagModel.tenant_id == DEFAULT_TENANT_ID,
                    TagModel.name.in_(normalized_names),
                )
            ).all()
        )
        return [name for name in normalized_names if name not in existing_names]

    def list_tags(self) -> list[TagItem]:
        tags = self.session.scalars(
            select(TagModel).where(TagModel.tenant_id == DEFAULT_TENANT_ID).order_by(TagModel.name.asc())
        ).all()
        return [self._to_tag_item(tag) for tag in tags]

    def create_tag(self, payload: TagCreate) -> TagItem:
        tag = self.ensure_tag(payload.name, color=payload.color, is_public=payload.is_public)
        self.session.commit()
        return self._to_tag_item(tag)

    def mark_duplicate(self, post_id: str, payload: DuplicateUpdate, actor: UserModel) -> PostItem:
        post = self.get_active_post_model(post_id)
        original = self.get_active_post_model(payload.original_post_id)
        post.status = "duplicate"
        post.duplicate_of_id = original.id
        post.updated_at = _utc_now()
        if post.response is None:
            post.response = PostResponseModel(
                id=uuid4().hex,
                post_id=post.id,
                user_id=actor.id,
                text=payload.text,
                responded_at=_utc_now(),
            )
        else:
            post.response.text = payload.text
            post.response.user_id = actor.id
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

    def archive_post(self, post_id: str, actor: UserModel) -> PostItem | None:
        post = self.get_active_post_model(post_id)
        if post is None:
            return None
        item = self._to_post_item(post)
        post.archived_at = _utc_now()
        post.archived_by_user_id = actor.id
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
            created_at=_utc_now(),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def ensure_feishu_user(self, open_id: str, name: str | None = None) -> UserModel:
        user = self.session.scalar(
            select(UserModel).where(UserModel.tenant_id == DEFAULT_TENANT_ID, UserModel.feishu_open_id == open_id)
        )
        display_name = name.strip() if name and name.strip() else None
        if user is not None:
            if display_name is not None and user.name != display_name:
                user.name = display_name
                self.session.add(user)
                self.session.flush()
            return user

        user = UserModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            external_id=f"feishu:{open_id}",
            feishu_open_id=open_id,
            name=display_name or "Feishu User",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def get_imported_feishu_message(self, message_id: str) -> FeishuImportedMessageModel | None:
        return self.session.scalar(
            select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == message_id)
        )

    def get_imported_feishu_messages(
        self,
        message_ids: list[str],
    ) -> dict[str, FeishuImportedMessageModel]:
        if not message_ids:
            return {}
        records = self.session.scalars(
            select(FeishuImportedMessageModel).where(
                FeishuImportedMessageModel.message_id.in_(message_ids)
            )
        ).all()
        return {record.message_id: record for record in records}

    def get_feishu_thread_messages(
        self,
        *,
        chat_id: str,
        thread_ids: set[str],
        limit: int = 50,
    ) -> list[FeishuImportedMessageModel]:
        if not thread_ids:
            return []
        records = self.session.scalars(
            select(FeishuImportedMessageModel)
            .where(
                FeishuImportedMessageModel.chat_id == chat_id,
                or_(
                    FeishuImportedMessageModel.message_id.in_(thread_ids),
                    FeishuImportedMessageModel.root_id.in_(thread_ids),
                    FeishuImportedMessageModel.parent_id.in_(thread_ids),
                ),
            )
            .order_by(FeishuImportedMessageModel.sent_at.asc(), FeishuImportedMessageModel.created_at.asc())
            .limit(limit)
        ).all()
        return list(records)

    def record_feishu_import(
        self,
        *,
        message_id: str,
        chat_id: str,
        sender_open_id: str | None,
        sender_name: str | None,
        raw_text: str,
        status: str,
        chat_name: str | None = None,
        root_id: str | None = None,
        parent_id: str | None = None,
        sent_at: datetime | None = None,
        post_id: str | None = None,
        is_direct_source: bool = False,
        error: str | None = None,
    ) -> FeishuImportedMessageModel:
        existing = self.get_imported_feishu_message(message_id)
        if existing is not None:
            if existing.status != "failed":
                return existing
            existing.chat_id = chat_id
            existing.chat_name = chat_name
            existing.root_id = root_id
            existing.parent_id = parent_id
            existing.sender_open_id = sender_open_id
            existing.sender_name = sender_name
            existing.sent_at = sent_at
            existing.raw_text = raw_text
            existing.status = status
            existing.post_id = post_id
            existing.is_direct_source = is_direct_source
            existing.error = error[:2000] if error else None
            existing.updated_at = _utc_now()
            self.session.commit()
            return existing

        record = FeishuImportedMessageModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            message_id=message_id,
            chat_id=chat_id,
            chat_name=chat_name,
            root_id=root_id,
            parent_id=parent_id,
            sender_open_id=sender_open_id,
            sender_name=sender_name,
            sent_at=sent_at,
            post_id=post_id,
            is_direct_source=is_direct_source,
            status=status,
            error=error[:2000] if error else None,
            raw_text=raw_text,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        self.session.add(record)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.get_imported_feishu_message(message_id)
            if existing is not None:
                if existing.status == "failed":
                    existing.chat_id = chat_id
                    existing.chat_name = chat_name
                    existing.root_id = root_id
                    existing.parent_id = parent_id
                    existing.sender_open_id = sender_open_id
                    existing.sender_name = sender_name
                    existing.sent_at = sent_at
                    existing.raw_text = raw_text
                    existing.status = status
                    existing.post_id = post_id
                    existing.is_direct_source = is_direct_source
                    existing.error = error[:2000] if error else None
                    existing.updated_at = _utc_now()
                    self.session.commit()
                return existing
            raise
        return record

    def get_post_sources(self, post_id: str, *, context_limit: int = 50) -> PostSourcesResponse:
        direct_records = list(
            self.session.scalars(
                select(FeishuImportedMessageModel)
                .where(
                    FeishuImportedMessageModel.post_id == post_id,
                    or_(
                        FeishuImportedMessageModel.is_direct_source.is_(True),
                        FeishuImportedMessageModel.post_id.is_not(None),
                    ),
                )
                .order_by(FeishuImportedMessageModel.sent_at.asc(), FeishuImportedMessageModel.created_at.asc())
            ).all()
        )
        if not direct_records:
            return PostSourcesResponse(groups=[])

        direct_ids = {record.message_id for record in direct_records}
        grouped: dict[tuple[str, str], list[FeishuImportedMessageModel]] = {}
        group_kinds: dict[tuple[str, str], str] = {}
        for direct in direct_records:
            thread_key = direct.root_id or direct.parent_id
            if thread_key:
                key = (direct.chat_id, thread_key)
                group_kinds[key] = "thread"
                thread_records = self.get_feishu_thread_messages(
                    chat_id=direct.chat_id,
                    thread_ids={thread_key, direct.message_id},
                    limit=context_limit,
                )
                grouped.setdefault(key, []).extend(thread_records)
                continue

            sent_at = direct.sent_at or direct.created_at
            key = (direct.chat_id, f"window:{sent_at.isoformat()}")
            group_kinds[key] = "window"
            start = sent_at - timedelta(minutes=60)
            end = sent_at + timedelta(minutes=60)
            window_records = self.session.scalars(
                select(FeishuImportedMessageModel)
                .where(
                    FeishuImportedMessageModel.chat_id == direct.chat_id,
                    func.coalesce(FeishuImportedMessageModel.sent_at, FeishuImportedMessageModel.created_at).between(start, end),
                )
                .order_by(FeishuImportedMessageModel.sent_at.asc(), FeishuImportedMessageModel.created_at.asc())
                .limit(context_limit)
            ).all()
            grouped.setdefault(key, []).extend(window_records)

        result: list[PostSourceGroupItem] = []
        for (chat_id, key), records in grouped.items():
            unique = {record.message_id: record for record in records}
            ordered = sorted(
                unique.values(),
                key=lambda item: (_datetime_sort_value(item.sent_at or item.created_at), item.message_id),
            )
            chat_name = next((item.chat_name for item in ordered if item.chat_name), None) or chat_id
            result.append(
                PostSourceGroupItem(
                    key=key,
                    kind=group_kinds[(chat_id, key)],
                    chat_id=chat_id,
                    chat_name=chat_name,
                    messages=[
                        PostSourceMessageItem(
                            message_id=item.message_id,
                            chat_id=item.chat_id,
                            chat_name=item.chat_name or item.chat_id,
                            sender_open_id=item.sender_open_id,
                            sender_name=item.sender_name,
                            sent_at=item.sent_at,
                            root_id=item.root_id,
                            parent_id=item.parent_id,
                            raw_text=item.raw_text,
                            is_direct_source=item.message_id in direct_ids,
                        )
                        for item in ordered[:context_limit]
                    ],
                )
            )
        result.sort(
            key=lambda group: _datetime_sort_value(
                group.messages[0].sent_at or datetime.min.replace(tzinfo=timezone.utc)
            )
        )
        return PostSourcesResponse(groups=result)

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

    def _get_tags_by_names(self, names: list[str]) -> list[TagModel]:
        normalized_names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        if not normalized_names:
            return []
        tags = self.session.scalars(
            select(TagModel).where(
                TagModel.tenant_id == DEFAULT_TENANT_ID,
                TagModel.name.in_(normalized_names),
            )
        ).all()
        tags_by_name = {tag.name: tag for tag in tags}
        return [tags_by_name[name] for name in normalized_names]

    def _post_select(self):
        return select(PostModel).where(PostModel.archived_at.is_(None)).options(
            selectinload(PostModel.user),
            selectinload(PostModel.tags),
            selectinload(PostModel.votes),
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
            has_voted=False,
            user=self._to_user_item(post.user),
            tags=[self._to_tag_item(tag) for tag in post.tags],
            response=self._to_response_item(post.response) if post.response else None,
            duplicate_of=duplicate_of,
            linked_task=self._to_linked_task_item(post.linked_task) if post.linked_task and post.linked_task.archived_at is None else None,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    def _to_tag_item(self, tag: TagModel) -> TagItem:
        return TagItem(id=tag.id, name=tag.name, slug=tag.slug, color=tag.color, is_public=tag.is_public)

    def _to_user_item(self, user: UserModel):
        return {"id": user.id, "name": user.name}

    def _to_response_item(self, response: PostResponseModel):
        return {"text": response.text, "responded_at": response.responded_at, "user": self._to_user_item(response.user)}

    def _to_linked_task_item(self, task):
        return {"id": task.id, "number": task.number, "title": task.title, "status": task.status}

def seed_default_data(session: Session) -> None:
    PostsRepository(session).ensure_seed_data()


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "item"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_sort_value(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
