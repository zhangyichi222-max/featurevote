from collections.abc import Sequence
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.clients.feishu import FeishuChatMessage
from app.core.config import settings
from app.db.base import Base
from app.models.post import FeishuImportedMessageModel, PostModel, UserModel, VoteModel
from app.repositories.posts import DEFAULT_TENANT_ID, PostsRepository, seed_default_data
from app.schemas.ai import SuggestionDraftResponse
from app.schemas.post import PostCreate
from app.services.feishu_import import FeishuRequirementImportService


def test_import_creates_new_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([_message("om_1", text="希望支持按部门导出投票结果，方便复盘每个团队最关心的需求。")]),
        deepseek_client=FakeDeepSeekClient(),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.created == 1
    assert stats.fetched == 1
    post = session.scalar(select(PostModel).where(PostModel.title == "Export votes by department"))
    assert post is not None
    assert [tag.name for tag in post.tags] == ["飞书导入"]
    record = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_1"))
    assert record is not None
    assert record.status == "created"
    assert record.post_id == post.id


def test_import_skips_previously_processed_message(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    message = _message("om_1", text="希望支持按部门导出投票结果，方便复盘每个团队最关心的需求。")
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=FakeDeepSeekClient(),
    )

    first = asyncio.run(service.import_configured_chats())
    second = asyncio.run(service.import_configured_chats())

    assert first.created == 1
    assert second.skipped == 1
    assert session.scalar(select(PostModel).where(PostModel.title == "Export votes by department")).number == 1


def test_import_votes_for_duplicate_from_different_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    creator = _add_user(session, "creator", "ou_creator")
    original = PostsRepository(session).create_post(
        PostCreate(
            title="Export votes by department",
            description="Let admins export vote totals grouped by department.",
            tags=[],
        ),
        creator,
    )
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([_message("om_2", sender_open_id="ou_voter")]),
        deepseek_client=FakeDeepSeekClient(),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.voted == 1
    assert session.scalar(select(VoteModel).where(VoteModel.post_id == original.id)) is not None
    record = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_2"))
    assert record.status == "voted"
    assert record.post_id == original.id


def test_import_records_already_voted_for_same_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    creator = _add_user(session, "creator", "ou_creator")
    original = PostsRepository(session).create_post(
        PostCreate(
            title="Export votes by department",
            description="Let admins export vote totals grouped by department.",
            tags=[],
        ),
        creator,
    )
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([
            _message("om_2", sender_open_id="ou_voter"),
            _message("om_3", sender_open_id="ou_voter"),
        ]),
        deepseek_client=FakeDeepSeekClient(),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.voted == 1
    assert stats.already_voted == 1
    assert len(session.scalars(select(VoteModel).where(VoteModel.post_id == original.id)).all()) == 1
    record = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_3"))
    assert record.status == "already_voted"


def test_import_records_failed_message_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([
            _message("om_bad", text="这是一条会触发 AI 失败但长度足够的飞书需求消息。"),
            _message("om_good", text="希望支持按部门导出投票结果，方便复盘每个团队最关心的需求。"),
        ]),
        deepseek_client=FakeDeepSeekClient(fail_ids={"这是一条会触发 AI 失败但长度足够的飞书需求消息。"}),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.failed == 1
    assert stats.created == 1
    failed = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_bad"))
    assert failed.status == "failed"
    assert "AI unavailable" in failed.error


class FakeFeishuClient:
    def __init__(self, messages: Sequence[FeishuChatMessage]) -> None:
        self.messages = list(messages)

    def list_chat_text_messages(self, chat_id: str, *, page_size: int = 50, page_token: str | None = None):
        _ = chat_id, page_size, page_token
        return self.messages, None


class FakeDeepSeekClient:
    def __init__(self, fail_ids: set[str] | None = None) -> None:
        self.fail_ids = fail_ids or set()

    async def draft_suggestion(self, idea: str) -> SuggestionDraftResponse:
        if idea in self.fail_ids:
            raise HTTPException(status_code=503, detail="AI unavailable")
        return SuggestionDraftResponse(
            title="Export votes by department",
            description="Let admins export vote totals grouped by department.",
        )


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


def _configure(monkeypatch: pytest.MonkeyPatch, *, chat_ids: list[str]) -> None:
    monkeypatch.setattr(settings, "feishu_import_chat_ids", chat_ids)
    monkeypatch.setattr(settings, "feishu_import_batch_size", 50)
    monkeypatch.setattr(settings, "feishu_import_min_text_chars", 20)
    monkeypatch.setattr(settings, "feishu_import_duplicate_threshold", 0.72)
    monkeypatch.setattr(settings, "feishu_import_default_tags", ["飞书导入"])


def _message(
    message_id: str,
    *,
    sender_open_id: str = "ou_alice",
    text: str = "希望支持按部门导出投票结果，方便复盘每个团队最关心的需求。",
) -> FeishuChatMessage:
    return FeishuChatMessage(
        message_id=message_id,
        chat_id="oc_test",
        sender_open_id=sender_open_id,
        sender_name="Alice",
        sender_type="user",
        text=text,
        sent_at=None,
    )


def _add_user(session, user_id: str, open_id: str) -> UserModel:
    user = UserModel(
        id=user_id,
        tenant_id=DEFAULT_TENANT_ID,
        external_id=f"external-{user_id}",
        feishu_open_id=open_id,
        name=user_id,
        role="visitor",
    )
    session.add(user)
    session.commit()
    return user
