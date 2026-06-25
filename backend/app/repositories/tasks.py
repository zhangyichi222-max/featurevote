from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.post import NotificationTaskModel, PostModel, TagModel, TaskModel, UserModel, utc_now
from app.repositories.posts import DEFAULT_TENANT_ID
from app.schemas.post import UserItem
from app.schemas.task import TaskCreate, TaskItem, TaskLabelCreate, TaskLabelItem, TaskUpdate

TASK_NOTIFICATION_MAX_ATTEMPTS = 3


class TasksRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_tasks(
        self,
        query: str = "",
        statuses: list[str] | None = None,
        assignee_id: str = "",
        labels: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TaskItem], int]:
        statement = self._task_select()
        count_statement = select(func.count(TaskModel.id)).where(TaskModel.archived_at.is_(None))

        if statuses:
            status_filter = TaskModel.status.in_(statuses)
            statement = statement.where(status_filter)
            count_statement = count_statement.where(status_filter)

        if assignee_id:
            assignee_filter = TaskModel.assignee_user_id == assignee_id
            statement = statement.where(assignee_filter)
            count_statement = count_statement.where(assignee_filter)

        if query:
            cleaned_query = query.strip().lower()
            term = f"%{cleaned_query}%"
            query_conditions = [
                func.lower(TaskModel.title).like(term),
                func.lower(TaskModel.description_markdown).like(term),
            ]
            if cleaned_query.startswith("task-") and cleaned_query[5:].isdigit():
                query_conditions.append(TaskModel.number == int(cleaned_query[5:]))
            query_filter = or_(*query_conditions)
            statement = statement.where(query_filter)
            count_statement = count_statement.where(query_filter)

        if labels:
            label_filter = TaskModel.labels.any(TagModel.slug.in_(labels))
            statement = statement.where(label_filter)
            count_statement = count_statement.where(label_filter)

        total = int(self.session.scalar(count_statement) or 0)
        records = self.session.scalars(
            statement
            .order_by(TaskModel.updated_at.desc(), TaskModel.number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).unique().all()
        return [self._to_task_item(record) for record in records], total

    def get_task(self, task_id: str) -> TaskItem | None:
        task = self.get_task_model(task_id)
        return self._to_task_item(task) if task else None

    def get_task_model(self, task_id: str) -> TaskModel | None:
        return self.session.scalars(self._task_select().where(TaskModel.id == task_id)).first()

    def create_task(self, payload: TaskCreate, user: UserModel) -> TaskItem:
        task = TaskModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            number=self._next_task_number(),
            title=payload.title.strip(),
            description_markdown=payload.description_markdown,
            status=payload.status,
            assignee_user_id=payload.assignee_user_id,
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        task.labels = [self.ensure_label(label_name) for label_name in payload.labels]
        self.session.add(task)
        self.session.flush()
        if task.assignee is not None:
            self._enqueue_task_assignment_notification(task, task.assignee)
        self.session.commit()
        return self.get_task(task.id)

    def convert_post_to_task(self, post_id: str, payload: TaskCreate, actor: UserModel) -> tuple[object | None, TaskItem | None]:
        existing = self.session.scalar(
            select(TaskModel).where(
                TaskModel.tenant_id == DEFAULT_TENANT_ID,
                TaskModel.source_post_id == post_id,
                TaskModel.archived_at.is_(None),
            )
        )
        if existing is not None:
            return existing.source_post, self.get_task(existing.id)

        post = self._get_active_post(post_id)
        if post is None:
            return None, None

        task = TaskModel(
            id=uuid4().hex,
            tenant_id=DEFAULT_TENANT_ID,
            number=self._next_task_number(),
            title=payload.title.strip(),
            description_markdown=payload.description_markdown,
            status="todo",
            source_post_id=post.id,
            assignee_user_id=payload.assignee_user_id,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        task.labels = [self.ensure_label(label_name) for label_name in payload.labels]
        converted_at = utc_now()
        post.archived_at = converted_at
        post.archived_by_user_id = actor.id
        post.updated_at = converted_at
        self.session.add(task)
        self.session.add(post)
        self.session.flush()
        if task.assignee is not None:
            self._enqueue_task_assignment_notification(task, task.assignee)
        self.session.commit()
        return post, self.get_task(task.id)

    def user_exists(self, user_id: str) -> bool:
        return self.session.get(UserModel, user_id) is not None

    def update_task(self, task_id: str, payload: TaskUpdate, user: UserModel) -> TaskItem | None:
        task = self.get_task_model(task_id)
        if task is None:
            return None

        previous_status = task.status
        previous_assignee_id = task.assignee_user_id

        if payload.title is not None:
            task.title = payload.title.strip()
        if "assignee_user_id" in payload.model_fields_set:
            task.assignee_user_id = payload.assignee_user_id
        if payload.labels is not None:
            task.labels = [self.ensure_label(label_name) for label_name in payload.labels]

        if payload.description_markdown is not None:
            task.description_markdown = payload.description_markdown
        if payload.status is not None:
            task.status = payload.status

        task.updated_by_user_id = user.id
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.flush()

        if task.assignee_user_id and task.assignee_user_id != previous_assignee_id and task.assignee:
            self._enqueue_task_assignment_notification(task, task.assignee)
        if payload.status is not None and task.status != previous_status:
            self._enqueue_task_status_notification(task, previous_status, task.status)

        self.session.commit()
        return self.get_task(task.id)

    def delete_task(self, task_id: str, user: UserModel) -> TaskItem | None:
        task = self.get_task_model(task_id)
        if task is None:
            return None

        item = self._to_task_item(task)
        deleted_at = utc_now()
        task.archived_at = deleted_at
        task.updated_by_user_id = user.id
        task.updated_at = deleted_at

        self.session.add(task)
        self.session.commit()
        return item

    def list_labels(self) -> list[TaskLabelItem]:
        labels = self.session.scalars(
            select(TagModel).where(TagModel.tenant_id == DEFAULT_TENANT_ID).order_by(TagModel.name.asc())
        ).all()
        return [self._to_label_item(label) for label in labels]

    def create_label(self, payload: TaskLabelCreate) -> TaskLabelItem:
        label = self.ensure_label(payload.name, color=payload.color)
        self.session.commit()
        return self._to_label_item(label)

    def delete_label(self, label_id: str) -> bool:
        label = self.session.get(TagModel, label_id)
        if label is None or label.tenant_id != DEFAULT_TENANT_ID:
            return False
        label.posts.clear()
        label.tasks.clear()
        self.session.delete(label)
        self.session.commit()
        return True

    def list_assignees(self) -> list[UserItem]:
        users = self.session.scalars(
            select(UserModel).where(UserModel.tenant_id == DEFAULT_TENANT_ID).order_by(UserModel.name.asc())
        ).all()
        return [self._to_user_item(user) for user in users]

    def ensure_label(self, name: str, color: str = "#2f75d6") -> TagModel:
        name = name.strip()
        slug = _slugify(name)
        label = self.session.scalar(
            select(TagModel).where(TagModel.tenant_id == DEFAULT_TENANT_ID, TagModel.slug == slug)
        )
        if label is not None:
            return label
        label = TagModel(id=uuid4().hex, tenant_id=DEFAULT_TENANT_ID, name=name, slug=slug, color=color, is_public=True)
        self.session.add(label)
        self.session.flush()
        return label

    def _task_select(self):
        return select(TaskModel).where(TaskModel.archived_at.is_(None)).options(
            selectinload(TaskModel.assignee),
            selectinload(TaskModel.created_by),
            selectinload(TaskModel.updated_by),
            selectinload(TaskModel.source_post),
            selectinload(TaskModel.labels),
        )

    def _get_active_post(self, post_id: str) -> PostModel | None:
        return self.session.scalar(
            select(PostModel).where(
                PostModel.id == post_id,
                PostModel.tenant_id == DEFAULT_TENANT_ID,
                PostModel.archived_at.is_(None),
                PostModel.status != "duplicate",
            )
        )

    def _next_task_number(self) -> int:
        value = self.session.scalar(
            select(func.coalesce(func.max(TaskModel.number), 0)).where(TaskModel.tenant_id == DEFAULT_TENANT_ID)
        )
        return int(value) + 1

    def _enqueue_task_assignment_notification(self, task: TaskModel, assignee: UserModel) -> None:
        self._enqueue_notification(
            task=task,
            user=assignee,
            recipient_open_id=assignee.feishu_open_id,
            event_type="task_assigned",
            dedupe_key=f"assignee:{task.assignee_user_id}:{task.updated_at.isoformat()}",
            message="\n".join(
                [
                    "你有一个新的开发任务",
                    f"任务：TASK-{task.number} {task.title}",
                    f"状态：{task.status}",
                    f"链接：{settings.frontend_base_url}/?view=tasks&task={task.id}",
                ]
            ),
        )

    def _enqueue_task_status_notification(self, task: TaskModel, previous_status: str, new_status: str) -> None:
        recipients: dict[str, tuple[str, str | None]] = {}
        for user in self.session.scalars(select(UserModel).where(UserModel.tenant_id == DEFAULT_TENANT_ID)):
            recipients[user.id] = (user.id, user.feishu_open_id)

        for recipient_key, (user_id, open_id) in recipients.items():
            self._enqueue_notification(
                task=task,
                user_id=user_id,
                recipient_open_id=open_id,
                event_type="task_status_changed",
                dedupe_key=f"status:{previous_status}:{new_status}:{recipient_key}",
                message="\n".join(
                    [
                        "开发任务状态已更新",
                        f"任务：TASK-{task.number} {task.title}",
                        f"状态：{previous_status} -> {new_status}",
                        f"链接：{settings.frontend_base_url}/?view=tasks&task={task.id}",
                    ]
                ),
            )

    def _enqueue_notification(
        self,
        task: TaskModel,
        recipient_open_id: str | None,
        event_type: str,
        dedupe_key: str,
        message: str,
        user: UserModel | None = None,
        user_id: str | None = None,
    ) -> None:
        notification = NotificationTaskModel(
            id=uuid4().hex,
            tenant_id=task.tenant_id,
            post_id=None,
            task_id=task.id,
            user_id=user.id if user is not None else (user_id or task.created_by_user_id),
            recipient_open_id=recipient_open_id,
            event_type=event_type,
            dedupe_key=dedupe_key[:120],
            message=message,
            status="pending",
            attempts=0,
            max_attempts=TASK_NOTIFICATION_MAX_ATTEMPTS,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        nested = self.session.begin_nested()
        try:
            self.session.add(notification)
            self.session.flush()
            nested.commit()
        except IntegrityError:
            nested.rollback()

    def _to_task_item(self, task: TaskModel) -> TaskItem:
        return TaskItem(
            id=task.id,
            number=task.number,
            title=task.title,
            description_markdown=task.description_markdown,
            status=task.status,
            assignee=self._to_user_item(task.assignee) if task.assignee else None,
            created_by=self._to_user_item(task.created_by),
            updated_by=self._to_user_item(task.updated_by) if task.updated_by else None,
            source_post=(
                {"id": task.source_post.id, "number": task.source_post.number, "title": task.source_post.title, "status": task.source_post.status}
                if task.source_post
                else None
            ),
            labels=[self._to_label_item(label) for label in task.labels],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _to_label_item(self, label: TagModel) -> TaskLabelItem:
        return TaskLabelItem(id=label.id, name=label.name, slug=label.slug, color=label.color)

    def _to_user_item(self, user: UserModel) -> UserItem:
        return UserItem(id=user.id, name=user.name)


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "item"
