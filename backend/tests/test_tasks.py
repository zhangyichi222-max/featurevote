from sqlalchemy import select

from app.models.post import NotificationTaskModel, PostModel, UserModel
from app.repositories.posts import DEFAULT_TENANT_ID
from app.repositories.tasks import TasksRepository
from app.schemas.post import PostCreate
from app.schemas.task import TaskCreate, TaskLabelCreate, TaskUpdate
from app.services.tasks import TasksService
from app.tests_support import make_session


def test_admin_can_create_task_with_labels_and_assignment_notification() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    assignee = _add_user(session, "dev", "ou_dev")

    task = TasksRepository(session).create_task(
        TaskCreate(
            title="Build task board",
            description_markdown="**Ship it**",
            status="todo",
            assignee_user_id=assignee.id,
            labels=["Frontend"],
        ),
        admin,
    )

    assert task.number == 1
    assert task.assignee.id == assignee.id
    assert [label.name for label in task.labels] == ["Frontend"]
    notification = session.scalar(select(NotificationTaskModel).where(NotificationTaskModel.event_type == "task_assigned"))
    assert notification is not None
    assert notification.task_id == task.id
    assert notification.recipient_open_id == "ou_dev"


def test_assignee_can_only_update_status_and_description() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    assignee = _add_user(session, "dev", "ou_dev")
    task = TasksRepository(session).create_task(
        TaskCreate(title="Fix bug", description_markdown="Bug", assignee_user_id=assignee.id),
        admin,
    )

    updated = TasksRepository(session).update_task(
        task.id,
        TaskUpdate(description_markdown="Done soon", status="in_progress"),
        assignee,
        allow_admin_fields=False,
    )

    assert updated.status == "in_progress"
    assert updated.description_markdown == "Done soon"
    notification = session.scalar(select(NotificationTaskModel).where(NotificationTaskModel.event_type == "task_status_changed"))
    assert notification is not None
    assert "todo -> in_progress" in notification.message


def test_task_filters_by_status_assignee_label_and_query() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    dev = _add_user(session, "dev", "ou_dev")
    repo = TasksRepository(session)
    repo.create_task(TaskCreate(title="Frontend polish", assignee_user_id=dev.id, status="blocked", labels=["UI"]), admin)
    repo.create_task(TaskCreate(title="Backend cleanup", status="todo", labels=["API"]), admin)

    results = repo.list_tasks(query="front", statuses=["blocked"], assignee_id=dev.id, labels=["ui"])

    assert len(results) == 1
    assert results[0].title == "Frontend polish"


def test_create_task_rejects_missing_assignee() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    service = TasksService(TasksRepository(session))

    try:
        _run(service.create_task(TaskCreate(title="Bad assignee", assignee_user_id="missing"), admin))
    except Exception as exc:
        assert getattr(exc, "status_code") == 400
    else:
        raise AssertionError("Expected missing assignee to be rejected.")


def test_create_label_is_idempotent_by_slug() -> None:
    session = make_session()
    repo = TasksRepository(session)

    first = repo.create_label(TaskLabelCreate(name="QA", color="#111111"))
    second = repo.create_label(TaskLabelCreate(name="QA", color="#222222"))

    assert first.id == second.id
    assert len(repo.list_labels()) == 1


def test_convert_post_to_task_is_idempotent_and_sets_post_in_progress() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    post = _add_post(session, admin)
    repo = TasksRepository(session)

    _post, task = repo.convert_post_to_task(
        post.id,
        TaskCreate(title="Ship export", description_markdown="From requirement", labels=["需求转入"]),
        admin,
    )
    _post_again, task_again = repo.convert_post_to_task(
        post.id,
        TaskCreate(title="Different title", description_markdown="Duplicate attempt", labels=[]),
        admin,
    )

    assert task.id == task_again.id
    assert task.source_post.id == post.id
    assert session.get(PostModel, post.id).status == "in_progress"
    assert len(repo.list_tasks()) == 1


def test_task_done_and_canceled_sync_source_post_status() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    post = _add_post(session, admin)
    repo = TasksRepository(session)
    _post, task = repo.convert_post_to_task(
        post.id,
        TaskCreate(title="Ship export", description_markdown="From requirement"),
        admin,
    )

    repo.update_task(task.id, TaskUpdate(status="done"), admin, allow_admin_fields=True)
    assert session.get(PostModel, post.id).status == "completed"

    other_post = _add_post(session, admin, title="Cancel export")
    _other_post, other_task = repo.convert_post_to_task(
        other_post.id,
        TaskCreate(title="Cancel export", description_markdown="From requirement"),
        admin,
    )
    repo.update_task(other_task.id, TaskUpdate(status="canceled"), admin, allow_admin_fields=True)

    assert session.get(PostModel, other_post.id).status == "declined"


def test_upload_image_validation_and_storage() -> None:
    session = make_session()
    service = TasksService(TasksRepository(session), image_storage=FakeStorage())

    result = _run(service.upload_image(b"image", "image/png", "demo.png"))

    assert result.url == "http://minio/task-images/demo.png"


class FakeStorage:
    def upload_image(self, content: bytes, content_type: str, filename: str) -> str:
        assert content == b"image"
        assert content_type == "image/png"
        return "http://minio/task-images/demo.png"


def _add_user(session, user_id: str, open_id: str, role: str = "visitor") -> UserModel:
    user = UserModel(
        id=user_id,
        tenant_id=DEFAULT_TENANT_ID,
        external_id=open_id,
        feishu_open_id=open_id,
        name=user_id,
        role=role,
    )
    session.add(user)
    session.commit()
    return user


def _add_post(session, user: UserModel, title: str = "Need export") -> PostModel:
    from app.repositories.posts import PostsRepository

    item = PostsRepository(session).create_post(
        PostCreate(title=title, description="Export would help", tags=[]),
        user,
    )
    return session.get(PostModel, item.id)


def _run(coro):
    import asyncio

    return asyncio.run(coro)
