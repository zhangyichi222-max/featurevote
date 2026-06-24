from collections.abc import Sequence
import asyncio
import logging
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
from app.services.feishu_import import FeishuRequirementImportService, _content_preview


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
    assert second.fetched == 0
    assert second.skipped == 0
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
    assert second.fetched == 0
    assert second.skipped == 0
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


def test_grouped_import_keeps_short_messages_links_commands_and_other_bots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    start = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    messages = [
        _message("om_1", text="群历史消息", sent_at=start),
        _message("om_2", text="能自动生成任务吗？", sent_at=start + timedelta(minutes=1)),
        _message("om_3", text="可以吗", sent_at=start + timedelta(minutes=2)),
        _message("om_4", text="https://example.com/spec", sent_at=start + timedelta(minutes=3)),
        _message("om_5", text="python sync.py --dry-run", sent_at=start + timedelta(minutes=4)),
        _message(
            "om_6",
            text="机器人补充的上下文",
            sender_type="bot",
            sent_at=start + timedelta(minutes=5),
        ),
    ]
    deepseek_client = CapturingGroupedDeepSeekClient([
        FeishuRequirementDraft(
            title="从群历史消息生成任务",
            description="问题：历史讨论无法自动转成任务。\n\n场景：群内确认需求后需要人工整理。\n\n期望结果：系统自动从历史消息创建任务。",
            source_message_ids=[message.message_id for message in messages],
            confidence=0.9,
        )
    ])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient(messages),
        deepseek_client=deepseek_client,
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.fetched == 6
    assert stats.grouped_messages == 6
    assert stats.created == 1
    assert [message.message_id for message in deepseek_client.windows[0]] == [
        message.message_id for message in messages
    ]


def test_grouped_import_filters_only_definitely_invalid_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    start = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    valid_bot = _message(
        "om_bot_context",
        text="普通机器人提供的上下文",
        sender_type="bot",
        sent_at=start,
    )
    messages = [
        _message("om_blank", text="   ", sent_at=start),
        _message("om_recalled", text="This message was recalled", sent_at=start),
        _message(
            "om_summary",
            text="FeatureVote 需求导入已完成\n读取消息：10",
            sender_type="bot",
            sent_at=start,
        ),
        valid_bot,
    ]
    deepseek_client = CapturingGroupedDeepSeekClient([])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient(messages),
        deepseek_client=deepseek_client,
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.skipped == 4
    assert len(deepseek_client.windows) == 1
    assert [message.message_id for message in deepseek_client.windows[0]] == ["om_bot_context"]


def test_explicit_test_requirement_reaches_deepseek_and_creates_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    message = _message(
        "om_explicit",
        text="生成一个测试需求，功能为能否正常从群组历史消息中创建对应的任务",
        sent_at=datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc),
    )
    deepseek_client = CapturingGroupedDeepSeekClient([
        FeishuRequirementDraft(
            title="从群组历史消息创建任务",
            description="问题：无法确认历史消息能否创建任务。\n\n场景：验证飞书历史消息导入流程。\n\n期望结果：从群组历史消息创建对应任务。",
            source_message_ids=["om_explicit"],
            confidence=0.9,
        )
    ])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=deepseek_client,
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.created == 1
    assert deepseek_client.windows[0][0].text == message.text


def test_link_and_command_only_window_still_reaches_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    start = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    messages = [
        _message("om_link", text="https://example.com/spec", sent_at=start),
        _message("om_command", text="python sync.py --dry-run", sent_at=start + timedelta(minutes=1)),
    ]
    deepseek_client = CapturingGroupedDeepSeekClient([])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient(messages),
        deepseek_client=deepseek_client,
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.windows_processed == 1
    assert stats.skipped == 2
    assert [message.message_id for message in deepseek_client.windows[0]] == ["om_link", "om_command"]


def test_invalid_deepseek_candidate_is_logged_and_recorded_as_failed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    monkeypatch.setattr(settings, "feishu_import_debug_logging", True)
    message = _message(
        "om_invalid_candidate",
        text="生成一个测试需求",
        sent_at=datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc),
    )
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=InvalidGroupedDeepSeekClient(),
    )

    with caplog.at_level(logging.INFO, logger="app.services.feishu_import"):
        stats = asyncio.run(service.import_configured_chats())

    record = session.scalar(
        select(FeishuImportedMessageModel).where(
            FeishuImportedMessageModel.message_id == message.message_id
        )
    )
    assert stats.failed == 1
    assert record.status == "failed"
    assert "DeepSeek 返回格式无效" in caplog.text
    assert "候选需求格式无效" in caplog.text


def test_import_continues_pagination_after_fully_processed_page(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    repository = PostsRepository(session)
    old_message = _message("om_old", sent_at=datetime.now(timezone.utc) - timedelta(days=1))
    repository.record_feishu_import(
        message_id=old_message.message_id,
        chat_id=old_message.chat_id,
        sender_open_id=old_message.sender_open_id,
        sender_name=old_message.sender_name,
        raw_text=old_message.text,
        status="created",
    )
    new_message = _message("om_new", sent_at=datetime.now(timezone.utc) - timedelta(days=2))
    feishu_client = PagedFakeFeishuClient([
        ([old_message], "page-2"),
        ([new_message], None),
    ])
    deepseek_client = FakeDeepSeekClient()
    service = FeishuRequirementImportService(
        repository,
        feishu_client=feishu_client,
        deepseek_client=deepseek_client,
    )

    stats = asyncio.run(service.import_configured_chats())

    assert [call["page_token"] for call in feishu_client.calls] == [None, "page-2"]
    assert all(call["page_size"] == 50 for call in feishu_client.calls)
    assert all(call["end_time"] - call["start_time"] == timedelta(days=90) for call in feishu_client.calls)
    assert stats.fetched == 1
    assert stats.created == 1
    assert deepseek_client.ideas == [new_message.text]


def test_import_ignores_messages_older_than_ninety_days(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    recent = _message("om_recent", sent_at=datetime.now(timezone.utc) - timedelta(days=89))
    expired = _message("om_expired", sent_at=datetime.now(timezone.utc) - timedelta(days=91))
    deepseek_client = FakeDeepSeekClient()
    feishu_client = PagedFakeFeishuClient([
        ([recent, expired], "should-not-be-read"),
        ([_message("om_older", sent_at=datetime.now(timezone.utc) - timedelta(days=100))], None),
    ])
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=feishu_client,
        deepseek_client=deepseek_client,
    )

    stats = asyncio.run(service.import_configured_chats())

    assert stats.fetched == 1
    assert stats.created == 1
    assert len(feishu_client.calls) == 1
    assert deepseek_client.ideas == [recent.text]
    assert session.scalar(
        select(FeishuImportedMessageModel).where(
            FeishuImportedMessageModel.message_id == expired.message_id
        )
    ) is None


def test_failed_message_is_retried_and_record_is_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    message = _message("om_retry", sent_at=datetime.now(timezone.utc) - timedelta(days=1))
    repository = PostsRepository(session)
    failing_service = FeishuRequirementImportService(
        repository,
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=FakeDeepSeekClient(fail_ids={message.text}),
    )

    first = asyncio.run(failing_service.import_configured_chats())
    original_record = repository.get_imported_feishu_message(message.message_id)
    original_id = original_record.id
    assert first.failed == 1
    assert original_record.status == "failed"

    retry_client = FakeDeepSeekClient()
    retry_service = FeishuRequirementImportService(
        repository,
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=retry_client,
    )
    second = asyncio.run(retry_service.import_configured_chats())
    updated_record = repository.get_imported_feishu_message(message.message_id)

    assert second.fetched == 1
    assert second.created == 1
    assert retry_client.ideas == [message.text]
    assert updated_record.id == original_id
    assert updated_record.status == "created"
    assert updated_record.error is None
    assert session.scalars(
        select(FeishuImportedMessageModel).where(
            FeishuImportedMessageModel.message_id == message.message_id
        )
    ).all() == [updated_record]


def test_failed_message_failure_updates_existing_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"])
    message = _message("om_retry_failure", sent_at=datetime.now(timezone.utc) - timedelta(days=1))
    repository = PostsRepository(session)
    repository.record_feishu_import(
        message_id=message.message_id,
        chat_id=message.chat_id,
        sender_open_id=message.sender_open_id,
        sender_name=message.sender_name,
        raw_text=message.text,
        status="failed",
        error="old error",
    )
    service = FeishuRequirementImportService(
        repository,
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=FakeDeepSeekClient(
            fail_ids={message.text},
            failure_detail="new error",
        ),
    )

    stats = asyncio.run(service.import_configured_chats())
    record = repository.get_imported_feishu_message(message.message_id)

    assert stats.fetched == 1
    assert stats.failed == 1
    assert record.status == "failed"
    assert record.error == "new error"
    assert len(session.scalars(select(FeishuImportedMessageModel)).all()) == 1


def test_debug_logs_are_concise_and_hide_internal_ids(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _session()
    _configure(monkeypatch, chat_ids=["oc_test"], grouping_enabled=True)
    monkeypatch.setattr(settings, "feishu_import_debug_logging", True)
    message = _message(
        "om_secret_message_id",
        sender_open_id="ou_secret_open_id",
        text="希望支持按部门导出投票结果，方便团队复盘和确认后续优先级。",
        sent_at=datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc),
    )
    service = FeishuRequirementImportService(
        PostsRepository(session),
        feishu_client=FakeFeishuClient([message]),
        deepseek_client=GroupedDeepSeekClient([]),
    )

    with caplog.at_level(logging.INFO, logger="app.services.feishu_import"):
        stats = asyncio.run(service.import_configured_chats())

    output = caplog.text
    assert stats.skipped == 1
    assert "第 1 页：文本消息 1 条，已处理 0 条，失败重试 0 条，本次新增 1 条" in output
    assert "历史消息读取完成：共 1 页，待处理 1 条" in output
    assert "正在分析第 1/1 组，共 1 条消息" in output
    assert "DeepSeek 分析完成：模型未识别到需求" in output
    assert "om_secret_message_id" not in output
    assert "ou_secret_open_id" not in output


def test_content_preview_flattens_and_truncates_long_text() -> None:
    preview = _content_preview("第一行\n第二行  " + ("很长的内容" * 40), max_chars=24)

    assert "\n" not in preview
    assert len(preview) == 25
    assert preview.endswith("…")


class FakeFeishuClient:
    def __init__(self, messages: Sequence[FeishuChatMessage]) -> None:
        self.messages = list(messages)
        self.sent_messages: list[tuple[str, str]] = []

    def list_chat_text_messages(
        self,
        chat_id: str,
        *,
        page_size: int = 50,
        page_token: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ):
        _ = chat_id, page_size, page_token, start_time, end_time
        return self.messages, None

    def send_chat_text_message(self, chat_id: str, text: str, uuid: str | None = None) -> None:
        _ = uuid
        self.sent_messages.append((chat_id, text))


class PagedFakeFeishuClient(FakeFeishuClient):
    def __init__(self, pages: list[tuple[list[FeishuChatMessage], str | None]]) -> None:
        super().__init__([])
        self.pages = pages
        self.calls: list[dict] = []

    def list_chat_text_messages(
        self,
        chat_id: str,
        *,
        page_size: int = 50,
        page_token: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ):
        self.calls.append(
            {
                "chat_id": chat_id,
                "page_size": page_size,
                "page_token": page_token,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        return self.pages[len(self.calls) - 1]


class FakeDeepSeekClient:
    def __init__(
        self,
        fail_ids: set[str] | None = None,
        failure_detail: str = "AI unavailable",
    ) -> None:
        self.fail_ids = fail_ids or set()
        self.failure_detail = failure_detail
        self.ideas: list[str] = []

    async def draft_suggestion(self, idea: str) -> SuggestionDraftResponse:
        self.ideas.append(idea)
        if idea in self.fail_ids:
            raise HTTPException(status_code=503, detail=self.failure_detail)
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


class CapturingGroupedDeepSeekClient(GroupedDeepSeekClient):
    def __init__(self, drafts: list[FeishuRequirementDraft]) -> None:
        super().__init__(drafts)
        self.windows: list[list[FeishuChatMessage]] = []

    async def summarize_feishu_requirements(self, messages: list[FeishuChatMessage]) -> list[FeishuRequirementDraft]:
        self.windows.append(list(messages))
        return self.drafts


class InvalidGroupedDeepSeekClient(FakeDeepSeekClient):
    async def summarize_feishu_requirements(self, messages: list[FeishuChatMessage]) -> list[FeishuRequirementDraft]:
        _ = messages
        raise HTTPException(status_code=502, detail="候选需求格式无效")


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
    monkeypatch.setattr(settings, "feishu_import_duplicate_threshold", 0.72)
    monkeypatch.setattr(settings, "feishu_import_default_tags", ["Feishu Import"])
    monkeypatch.setattr(settings, "feishu_import_notify_chat", True)
    monkeypatch.setattr(settings, "feishu_import_grouping_enabled", grouping_enabled)
    monkeypatch.setattr(settings, "feishu_import_window_minutes", 60)
    monkeypatch.setattr(settings, "feishu_import_min_confidence", 0.65)
    monkeypatch.setattr(settings, "feishu_import_max_messages_per_summary", 50)
    monkeypatch.setattr(settings, "feishu_import_debug_logging", False)


def _message(
    message_id: str,
    *,
    sender_open_id: str = "ou_alice",
    sender_type: str = "user",
    text: str = "Need department export for vote results so teams can review priorities.",
    sent_at: datetime | None = None,
) -> FeishuChatMessage:
    return FeishuChatMessage(
        message_id=message_id,
        chat_id="oc_test",
        sender_open_id=sender_open_id,
        sender_name="Alice",
        sender_type=sender_type,
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
