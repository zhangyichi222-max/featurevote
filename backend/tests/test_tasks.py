import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Boolean, Column, ForeignKey, MetaData, String, Table, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models.post import NotificationTaskModel, PostModel, UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, PostsRepository
from app.repositories.tasks import TasksRepository
from app.schemas.post import PostCreate, TagCreate
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
    assert [label.slug for label in repo.list_labels()].count("qa") == 1


def test_task_labels_share_requirement_tag_catalog() -> None:
    session = make_session()
    posts_repo = PostsRepository(session)
    tasks_repo = TasksRepository(session)

    tag = posts_repo.create_tag(TagCreate(name="Shared", color="#123456"))
    label = tasks_repo.create_label(TaskLabelCreate(name="Shared", color="#654321"))

    assert label.id == tag.id
    assert label.color == "#123456"
    assert [item.id for item in tasks_repo.list_labels() if item.slug == "shared"] == [tag.id]


def test_task_label_creation_is_visible_from_requirement_tags() -> None:
    session = make_session()
    tasks_repo = TasksRepository(session)

    label = tasks_repo.create_label(TaskLabelCreate(name="Ops", color="#abcdef"))
    tags = PostsRepository(session).list_tags()

    assert any(tag.id == label.id and tag.slug == "ops" for tag in tags)


def test_shared_label_migration_merges_task_labels_by_slug() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table("tenants", metadata, Column("id", String(32), primary_key=True))
    Table(
        "tags",
        metadata,
        Column("id", String(32), primary_key=True),
        Column("tenant_id", String(32), nullable=False),
        Column("name", String(80), nullable=False),
        Column("slug", String(80), nullable=False),
        Column("color", String(24), nullable=False),
        Column("is_public", Boolean, nullable=False),
    )
    Table(
        "tasks",
        metadata,
        Column("id", String(32), primary_key=True),
        Column("tenant_id", String(32), nullable=False),
    )
    Table(
        "task_labels",
        metadata,
        Column("id", String(32), primary_key=True),
        Column("tenant_id", String(32), nullable=False),
        Column("name", String(80), nullable=False),
        Column("slug", String(80), nullable=False),
        Column("color", String(24), nullable=False),
    )
    Table(
        "task_label_links",
        metadata,
        Column("task_id", String(32), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        Column("label_id", String(32), ForeignKey("task_labels.id", ondelete="CASCADE"), primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(metadata.tables["tenants"].insert(), [{"id": DEFAULT_TENANT_ID}])
        connection.execute(
            metadata.tables["tags"].insert(),
            [
                {
                    "id": "tag-ui",
                    "tenant_id": DEFAULT_TENANT_ID,
                    "name": "UI",
                    "slug": "ui",
                    "color": "#111111",
                    "is_public": True,
                }
            ],
        )
        connection.execute(metadata.tables["tasks"].insert(), [{"id": "task-1", "tenant_id": DEFAULT_TENANT_ID}])
        connection.execute(
            metadata.tables["task_labels"].insert(),
            [
                {"id": "old-ui", "tenant_id": DEFAULT_TENANT_ID, "name": "UI old", "slug": "ui", "color": "#222222"},
                {"id": "old-api", "tenant_id": DEFAULT_TENANT_ID, "name": "API", "slug": "api", "color": "#333333"},
            ],
        )
        connection.execute(
            metadata.tables["task_label_links"].insert(),
            [{"task_id": "task-1", "label_id": "old-ui"}, {"task_id": "task-1", "label_id": "old-api"}],
        )

        migration = _load_shared_label_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = __import__("sqlalchemy").inspect(connection)
        assert "task_labels" not in inspector.get_table_names()
        link_rows = connection.execute(select(metadata.tables["task_label_links"])).mappings().all()
        tag_rows = connection.execute(select(metadata.tables["tags"])).mappings().all()

    assert {"task_id": "task-1", "label_id": "tag-ui"} in [dict(row) for row in link_rows]
    assert any(row["slug"] == "api" and row["color"] == "#333333" for row in tag_rows)
    assert len(link_rows) == 2


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


def test_delete_task_archives_task_and_source_post() -> None:
    session = make_session()
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    post = _add_post(session, admin)
    repo = TasksRepository(session)
    _post, task = repo.convert_post_to_task(
        post.id,
        TaskCreate(title="Ship export", description_markdown="From requirement"),
        admin,
    )

    deleted = repo.delete_task(task.id, admin)

    assert deleted.id == task.id
    assert repo.get_task(task.id) is None
    assert session.get(PostModel, post.id).archived_at is not None
    assert session.get(PostModel, post.id).archived_by_user_id == admin.id


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


def _load_shared_label_migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "202605201030_shared_task_requirement_labels.py"
    spec = importlib.util.spec_from_file_location("shared_task_requirement_labels", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
