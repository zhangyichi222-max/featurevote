import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.post import NotificationTaskModel, UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, HOT_VOTE_THRESHOLD, PostsRepository, seed_default_data
from app.schemas.post import PostCreate, StatusResponseUpdate
from app.services.notifications import NotificationProcessor


def test_status_change_enqueues_creator_notification() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    admin = _add_user(session, "admin", "ou_admin", role="admin")
    post = PostsRepository(session).create_post(PostCreate(title="Need exports", description="Please add export", tags=[]), creator)

    PostsRepository(session).set_response(
        post.id,
        StatusResponseUpdate(status="planned", text="We will plan this."),
        admin,
    )

    task = session.scalar(select(NotificationTaskModel))
    assert task is not None
    assert task.event_type == "status_changed"
    assert task.recipient_open_id == "ou_creator"
    assert "Need exports" in task.message
    assert "planned" in task.message
    assert "We will plan this." in task.message


def test_hot_notification_enqueues_once_at_threshold() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    post = PostsRepository(session).create_post(PostCreate(title="Need charts", description="Charts help", tags=[]), creator)

    for index in range(HOT_VOTE_THRESHOLD + 1):
        voter = _add_user(session, f"voter-{index}", f"ou_voter_{index}")
        PostsRepository(session).create_vote(post.id, voter)

    tasks = session.scalars(select(NotificationTaskModel).where(NotificationTaskModel.event_type == "hot")).all()
    refreshed = PostsRepository(session).get_active_post_model(post.id)
    assert refreshed.hot_at is not None
    assert len(tasks) == 1
    assert f"当前票数：{HOT_VOTE_THRESHOLD}" in tasks[0].message


def test_notification_processor_success_and_failure_paths() -> None:
    session = _session()
    task = _add_task(session, recipient_open_id="ou_creator")
    client = FakeFeishuClient()

    processed = NotificationProcessor(session, client).process_pending()

    assert processed == 1
    assert task.status == "sent"
    assert task.attempts == 1
    assert client.messages == [("ou_creator", "hello")]

    failing = _add_task(session, recipient_open_id="ou_fail", task_id="failing")
    client.raise_error = True
    NotificationProcessor(session, client).process_pending()

    assert failing.status == "pending"
    assert failing.attempts == 1
    assert failing.last_error == "boom"


def test_notification_processor_skips_missing_open_id() -> None:
    session = _session()
    task = _add_task(session, recipient_open_id=None)

    NotificationProcessor(session, FakeFeishuClient()).process_pending()

    assert task.status == "skipped"
    assert task.attempts == 0


class FakeFeishuClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.raise_error = False

    def send_text_message(self, open_id: str, text: str) -> None:
        if self.raise_error:
            raise RuntimeError("boom")
        self.messages.append((open_id, text))


def _session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)()
    seed_default_data(session)
    return session


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


def _add_task(session, recipient_open_id: str | None, task_id: str = "task") -> NotificationTaskModel:
    user = _add_user(session, f"user-{task_id}", recipient_open_id or f"missing-{task_id}")
    creator = user
    post = PostsRepository(session).create_post(
        PostCreate(title=f"Task {task_id}", description="Description", tags=[]),
        creator,
    )
    task = NotificationTaskModel(
        id=task_id,
        tenant_id=DEFAULT_TENANT_ID,
        post_id=post.id,
        user_id=user.id,
        recipient_open_id=recipient_open_id,
        event_type="status_changed",
        dedupe_key=f"dedupe-{task_id}",
        message="hello",
        status="pending",
        attempts=0,
        max_attempts=3,
    )
    session.add(task)
    session.commit()
    return task
