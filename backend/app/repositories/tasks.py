from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.post import NotificationTaskModel, TaskLabelModel, TaskModel, UserModel, utc_now
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
    ) -> list[TaskItem]:
        statement = self._task_select()

        if statuses:
            statement = statement.where(TaskModel.status.in_(statuses))

        if assignee_id:
            statement = statement.where(TaskModel.assignee_user_id == assignee_id)

        if query:
            term = f"%{query.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(TaskModel.title).like(term),
                    func.lower(TaskModel.description_markdown).like(term),
                )
            )

        if labels:
            statement = statement.join(TaskModel.labels).where(TaskLabelModel.slug.in_(labels))

        records = self.session.scalars(statement.order_by(TaskModel.updated_at.desc())).unique().all()
        return [self._to_task_item(record) for record in records]

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

    def user_exists(self, user_id: str) -> bool:
        return self.session.get(UserModel, user_id) is not None

    def update_task(self, task_id: str, payload: TaskUpdate, user: UserModel, allow_admin_fields: bool) -> TaskItem | None:
        task = self.get_task_model(task_id)
        if task is None:
            return None

        previous_status = task.status
        previous_assignee_id = task.assignee_user_id

        if allow_admin_fields:
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

        if allow_admin_fields and task.assignee_user_id and task.assignee_user_id != previous_assignee_id and task.assignee:
            self._enqueue_task_assignment_notification(task, task.assignee)
        if payload.status is not None and task.status != previous_status:
            self._enqueue_task_status_notification(task, previous_status, task.status)

        self.session.commit()
        return self.get_task(task.id)

    def list_labels(self) -> list[TaskLabelItem]:
        labels = self.session.scalars(
            select(TaskLabelModel).where(TaskLabelModel.tenant_id == DEFAULT_TENANT_ID).order_by(TaskLabelModel.name.asc())
        ).all()
        return [self._to_label_item(label) for label in labels]

    def create_label(self, payload: TaskLabelCreate) -> TaskLabelItem:
        label = self.ensure_label(payload.name, color=payload.color)
        self.session.commit()
        return self._to_label_item(label)

    def list_assignees(self) -> list[UserItem]:
        users = self.session.scalars(
            select(UserModel).where(UserModel.tenant_id == DEFAULT_TENANT_ID).order_by(UserModel.name.asc())
        ).all()
        return [self._to_user_item(user) for user in users]

    def ensure_label(self, name: str, color: str = "#2f75d6") -> TaskLabelModel:
        name = name.strip()
        slug = _slugify(name)
        label = self.session.scalar(
            select(TaskLabelModel).where(TaskLabelModel.tenant_id == DEFAULT_TENANT_ID, TaskLabelModel.slug == slug)
        )
        if label is not None:
            return label
        label = TaskLabelModel(id=uuid4().hex, tenant_id=DEFAULT_TENANT_ID, name=name, slug=slug, color=color)
        self.session.add(label)
        self.session.flush()
        return label

    def _task_select(self):
        return select(TaskModel).where(TaskModel.archived_at.is_(None)).options(
            selectinload(TaskModel.assignee),
            selectinload(TaskModel.created_by),
            selectinload(TaskModel.updated_by),
            selectinload(TaskModel.labels),
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
        if task.assignee is not None:
            recipients[task.assignee.id] = (task.assignee.id, task.assignee.feishu_open_id)
        for admin in self.session.scalars(select(UserModel).where(UserModel.tenant_id == DEFAULT_TENANT_ID, UserModel.role == "admin")):
            recipients[admin.id] = (admin.id, admin.feishu_open_id)
        for index, open_id in enumerate(settings.feishu_admin_open_ids):
            recipients[f"settings-admin-{index}"] = (task.updated_by_user_id or task.created_by_user_id, open_id)

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
            labels=[self._to_label_item(label) for label in task.labels],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _to_label_item(self, label: TaskLabelModel) -> TaskLabelItem:
        return TaskLabelItem(id=label.id, name=label.name, slug=label.slug, color=label.color)

    def _to_user_item(self, user: UserModel) -> UserItem:
        return UserItem(id=user.id, name=user.name, role=user.role)


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "label"
