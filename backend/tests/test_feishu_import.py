from collections.abc import Sequence
import asyncio
from datetime import datetime, timedelta, timezone

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
from app.schemas.ai import FeishuRequirementDraft, SuggestionDraftResponse
from app.schemas.post import PostCreate
from app.services.feishu_import import FeishuRequirementImportService


def test_import_creates_new_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([_message("om_1")]),
        deepseek_client=FakeDeepSeekClient(),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.created == 1
    assert stats.fetched == 1
    assert stats.created_titles == ["Export votes by department"]
    post = session.scalar(select(PostModel).where(PostModel.title == "Export votes by department"))
    assert post is not None
    assert [tag.name for tag in post.tags] == ["Feishu Import"]
    record = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_1"))
    assert record is not None
    assert record.status == "created"
    assert record.post_id == post.id


def test_import_skips_previously_processed_message(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    message = _message("om_1")
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=FakeDeepSeekClient(),
    )

    first = asyncio.run(service.import_configured_chats())
    second = asyncio.run(service.import_configured_chats())

    assert first.created == 1
    assert second.skipped == 1
    assert second.created_titles == []
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
    assert stats.created_titles == []
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
            _message("om_bad", text="This message makes AI fail but is long enough for import."),
            _message("om_good"),
        ]),
        deepseek_client=FakeDeepSeekClient(fail_ids={"This message makes AI fail but is long enough for import."}),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.failed == 1
    assert stats.created == 1
    assert stats.created_titles == ["Export votes by department"]
    failed = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_bad"))
    assert failed.status == "failed"
    assert "AI unavailable" in failed.error


def test_import_sends_chat_summary_with_created_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    feishu_client = FakeFeishuClient([_message("om_summary")])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=feishu_client,
        deepseek_client=FakeDeepSeekClient(),
    )

    stats = asyncio.run(service.import_configured_chats())
    second = asyncio.run(service.import_configured_chats())

    assert stats.created == 1
    assert second.skipped == 1
    assert len(feishu_client.sent_messages) == 1
    chat_id, summary = feishu_client.sent_messages[0]
    assert chat_id == "oc_test"
    assert "FeatureVote 需求导入已完成" in summary
    assert "新增需求：1" in summary
    assert "新增需求标题：" in summary
    assert "- Export votes by department" in summary


def test_grouped_import_creates_one_requirement_for_window(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    start = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    messages = [
        _message("om_1", text="需要一个稳定的测试部署流程，避免每次手动操作出错。", sent_at=start),
        _message("om_2", text="希望开发改完代码后可以一键部署到测试环境验证。", sent_at=start + timedelta(minutes=10)),
    ]
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient(messages),
        deepseek_client=GroupedDeepSeekClient([
            FeishuRequirementDraft(
                title="一键部署测试环境",
                description="问题：测试部署依赖手动步骤，容易出错。\n\n场景：开发完成代码后需要快速验证。\n\n期望结果：可以一键部署到测试环境。",
                source_message_ids=["om_1", "om_2"],
                confidence=0.9,
            )
        ]),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.windows_processed == 1
    assert stats.generated_requirements == 1
    assert stats.grouped_messages == 2
    assert stats.created == 1
    assert session.scalar(select(PostModel).where(PostModel.title == "一键部署测试环境")) is not None
    records = session.scalars(select(FeishuImportedMessageModel)).all()
    assert {record.message_id for record in records} == {"om_1", "om_2"}
    assert len({record.post_id for record in records}) == 1


def test_grouped_import_skips_low_confidence_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    message = _message("om_noise", text="需要看一下这段日志是不是正常，ok done success", sent_at=datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc))
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=GroupedDeepSeekClient([
            FeishuRequirementDraft(
                title="检查日志状态",
                description="问题：日志状态不清楚。\n\n场景：排查运行结果。\n\n期望结果：确认日志是否正常。",
                source_message_ids=["om_noise"],
                confidence=0.2,
            )
        ]),
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.created == 0
    assert stats.skipped == 1
    assert stats.low_confidence_skipped == 1
    record = session.scalar(select(FeishuImportedMessageModel).where(FeishuImportedMessageModel.message_id == "om_noise"))
    assert record.status == "skipped"


class FakeFeishuClient:
    def __init__(self, messages: Sequence[FeishuChatMessage]) -> None:
        self.messages = list(messages)
        self.sent_messages: list[tuple[str, str]] = []

    def list_chat_text_messages(self, chat_id: str, *, page_size: int = 50, page_token: str | None = None):
        _ = chat_id, page_size, page_token
        return self.messages, None

    def send_chat_text_message(self, chat_id: str, text: str, uuid: str | None = None) -> None:
        _ = uuid
        self.sent_messages.append((chat_id, text))


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


class GroupedDeepSeekClient(FakeDeepSeekClient):
    def __init__(self, drafts: list[FeishuRequirementDraft]) -> None:
        super().__init__()
        self.drafts = drafts

    async def summarize_feishu_requirements(self, messages: list[FeishuChatMessage]) -> list[FeishuRequirementDraft]:
        _ = messages
        return self.drafts


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


def _configure(monkeypatch: pytest.MonkeyPatch, *, chat_ids: list[str], grouping_enabled: bool = False) -> None:
    monkeypatch.setattr(settings, "feishu_import_chat_ids", chat_ids)
    monkeypatch.setattr(settings, "feishu_import_batch_size", 50)
    monkeypatch.setattr(settings, "feishu_import_min_text_chars", 20)
    monkeypatch.setattr(settings, "feishu_import_duplicate_threshold", 0.72)
    monkeypatch.setattr(settings, "feishu_import_default_tags", ["Feishu Import"])
    monkeypatch.setattr(settings, "feishu_import_notify_chat", True)
    monkeypatch.setattr(settings, "feishu_import_grouping_enabled", grouping_enabled)
    monkeypatch.setattr(settings, "feishu_import_window_minutes", 60)
    monkeypatch.setattr(settings, "feishu_import_min_confidence", 0.65)
    monkeypatch.setattr(settings, "feishu_import_max_messages_per_summary", 50)


def _message(
    message_id: str,
    *,
    sender_open_id: str = "ou_alice",
    text: str = "Need department export for vote results so teams can review priorities.",
    sent_at: datetime | None = None,
) -> FeishuChatMessage:
    return FeishuChatMessage(
        message_id=message_id,
        chat_id="oc_test",
        sender_open_id=sender_open_id,
        sender_name="Alice",
        sender_type="user",
        text=text,
        sent_at=sent_at,
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
