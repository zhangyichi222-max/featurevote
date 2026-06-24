import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.post import NotificationTaskModel, UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, PostsRepository, seed_default_data
from app.schemas.post import DuplicateUpdate, PostCreate, PostUpdate, StatusResponseUpdate
from app.services.notifications import NotificationProcessor


def test_status_change_enqueues_creator_notification() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    actor = _add_user(session, "actor", "ou_actor")
    post = PostsRepository(session).create_post(PostCreate(title="Need exports", description="Please add export", tags=[]), creator)

    PostsRepository(session).set_response(
        post.id,
        StatusResponseUpdate(status="planned", text="We will plan this."),
        actor,
    )

    task = session.scalar(select(NotificationTaskModel))
    assert task is not None
    assert task.event_type == "status_changed"
    assert task.recipient_open_id == "ou_creator"
    assert "Need exports" in task.message
    assert "planned" in task.message
    assert "We will plan this." in task.message


def test_duplicate_status_transition_dedupe_does_not_fail_update() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    actor = _add_user(session, "actor", "ou_actor")
    repo = PostsRepository(session)
    post = repo.create_post(PostCreate(title="Need dedupe", description="Dedupe", tags=[]), creator)

    repo.set_response(post.id, StatusResponseUpdate(status="planned", text="First."), actor)
    post_model = repo.get_active_post_model(post.id)
    post_model.status = "open"
    session.add(post_model)
    session.commit()
    repo.set_response(post.id, StatusResponseUpdate(status="planned", text="Second."), actor)

    tasks = session.scalars(select(NotificationTaskModel)).all()
    assert len(tasks) == 1


def test_votes_above_previous_threshold_only_record_votes() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    repo = PostsRepository(session)
    post = repo.create_post(PostCreate(title="Need charts", description="Charts help", tags=[]), creator)

    for index in range(11):
        voter = _add_user(session, f"voter-{index}", f"ou_voter_{index}")
        repo.create_vote(post.id, voter)

    tasks = session.scalars(select(NotificationTaskModel).where(NotificationTaskModel.event_type == "hot")).all()
    refreshed = repo.get_post(post.id)
    assert refreshed is not None
    assert refreshed.votes_count == 11
    assert tasks == []


def test_editing_post_content_does_not_enqueue_notification() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    repo = PostsRepository(session)
    post = repo.create_post(PostCreate(title="Original", description="Original", tags=[]), creator)

    updated = repo.update_post(
        post.id,
        PostUpdate(title="Updated", description="Updated description", tags=["Feature"]),
    )

    assert updated is not None
    assert updated.title == "Updated"
    assert session.scalars(select(NotificationTaskModel)).all() == []


def test_completed_and_declined_notifications_use_product_status_labels() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    actor = _add_user(session, "actor", "ou_actor")
    post = PostsRepository(session).create_post(PostCreate(title="Need status labels", description="Labels", tags=[]), creator)

    PostsRepository(session).set_response(post.id, StatusResponseUpdate(status="completed", text="Shipped."), actor)
    PostsRepository(session).set_response(post.id, StatusResponseUpdate(status="declined", text="Not planned."), actor)

    messages = [task.message for task in session.scalars(select(NotificationTaskModel)).all()]
    assert any("新状态：done" in message for message in messages)
    assert any("新状态：rejected" in message for message in messages)


def test_duplicate_and_archive_do_not_enqueue_notifications() -> None:
    session = _session()
    creator = _add_user(session, "creator", "ou_creator")
    actor = _add_user(session, "actor", "ou_actor")
    repo = PostsRepository(session)
    original = repo.create_post(PostCreate(title="Original", description="Original", tags=[]), creator)
    duplicate = repo.create_post(PostCreate(title="Duplicate", description="Duplicate", tags=[]), creator)

    repo.mark_duplicate(duplicate.id, DuplicateUpdate(original_post_id=original.id, text="Duplicate"), actor)
    repo.archive_post(original.id, actor)

    assert session.scalars(select(NotificationTaskModel)).all() == []


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


def test_notification_processor_stops_after_three_failures() -> None:
    session = _session()
    task = _add_task(session, recipient_open_id="ou_fail", task_id="exhaust")
    client = FakeFeishuClient()
    client.raise_error = True

    for _ in range(3):
        task.next_attempt_at = None
        task.status = "pending"
        session.add(task)
        session.commit()
        NotificationProcessor(session, client).process_pending()

    assert task.status == "failed"
    assert task.attempts == 3
    assert task.next_attempt_at is None


class FakeFeishuClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.raise_error = False

    def send_text_message(self, open_id: str, text: str, uuid: str | None = None) -> None:
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


def _add_user(session, user_id: str, open_id: str) -> UserModel:
    user = UserModel(
        id=user_id,
        tenant_id=DEFAULT_TENANT_ID,
        external_id=open_id,
        feishu_open_id=open_id,
        name=user_id,
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
