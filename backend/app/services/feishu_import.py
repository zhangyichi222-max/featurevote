from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.clients.deepseek import DeepSeekSuggestionClient
from app.clients.feishu import FeishuChatMessage, FeishuClient
from app.core.config import settings
from app.repositories.posts import PostsRepository
from app.schemas.ai import SimilarRequirementsRequest
from app.schemas.feishu_import import FeishuImportRunResponse
from app.schemas.post import PostCreate
from app.services.similarity import SimilarRequirementsService


logger = logging.getLogger(__name__)


class FeishuRequirementImportService:
    def __init__(
        self,
        repository: PostsRepository,
        feishu_client: FeishuClient | None = None,
        deepseek_client: DeepSeekSuggestionClient | None = None,
    ) -> None:
        self.repository = repository
        self.feishu_client = feishu_client or FeishuClient()
        self.deepseek_client = deepseek_client or DeepSeekSuggestionClient()

    async def import_configured_chats(self) -> FeishuImportRunResponse:
        stats = FeishuImportRunResponse()
        for chat_id in settings.feishu_import_chat_ids:
            await self.import_chat(chat_id, stats=stats)
        return stats

    async def import_chat(
        self,
        chat_id: str,
        *,
        stats: FeishuImportRunResponse | None = None,
    ) -> FeishuImportRunResponse:
        output = stats or FeishuImportRunResponse()
        before = _snapshot(output)
        page_token: str | None = None
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=90)
        page_size = max(1, min(settings.feishu_import_batch_size, 50))
        page_number = 0
        fetched_messages: list[FeishuChatMessage] = []
        while True:
            page_number += 1
            messages, page_token = self.feishu_client.list_chat_text_messages(
                chat_id,
                page_size=page_size,
                page_token=page_token,
                start_time=start_time,
                end_time=end_time,
            )
            reached_history_limit = any(
                message.sent_at is not None and message.sent_at < start_time
                for message in messages
            )
            messages = [
                message
                for message in messages
                if message.sent_at is None or message.sent_at >= start_time
            ]
            imported = self.repository.get_imported_feishu_messages(
                [message.message_id for message in messages]
            )
            already_processed = 0
            retries = 0
            actionable: list[FeishuChatMessage] = []
            for message in messages:
                record = imported.get(message.message_id)
                if record is None:
                    actionable.append(message)
                elif record.status == "failed":
                    actionable.append(message)
                    retries += 1
                else:
                    already_processed += 1
            output.add("fetched", len(actionable))
            fetched_messages.extend(actionable)
            if settings.feishu_import_debug_logging:
                logger.info(
                    "第 %s 页：文本消息 %s 条，已处理 %s 条，失败重试 %s 条，本次新增 %s 条",
                    page_number,
                    len(messages),
                    already_processed,
                    retries,
                    len(actionable) - retries,
                )
            if reached_history_limit or not page_token:
                break
        if settings.feishu_import_debug_logging:
            logger.info(
                "历史消息读取完成：共 %s 页，待处理 %s 条",
                page_number,
                len(fetched_messages),
            )
        if settings.feishu_import_grouping_enabled:
            await self._process_messages_grouped(fetched_messages, output)
        else:
            for message in fetched_messages:
                await self._process_message(message, output)
        self._notify_chat(chat_id, _delta(before, output))
        return output

    async def _process_messages_grouped(
        self,
        messages: list[FeishuChatMessage],
        stats: FeishuImportRunResponse,
    ) -> None:
        eligible: list[FeishuChatMessage] = []
        filtered_skipped = 0
        for message in messages:
            cleaned_text = message.text.strip()
            if self._is_definitely_invalid(message, cleaned_text):
                self._record(message, "skipped", raw_text=cleaned_text)
                stats.add("skipped")
                filtered_skipped += 1
                continue
            eligible.append(message)

        windows = _message_windows(eligible)
        if settings.feishu_import_debug_logging:
            logger.info(
                "消息筛选完成：过滤 %s 条，待分析 %s 条，共 %s 组",
                filtered_skipped,
                len(eligible),
                len(windows),
            )
        for index, window in enumerate(windows, start=1):
            stats.add("windows_processed")
            await self._process_message_window(
                window,
                stats,
                window_index=index,
                window_count=len(windows),
            )

    async def _process_message_window(
        self,
        messages: list[FeishuChatMessage],
        stats: FeishuImportRunResponse,
        *,
        window_index: int = 1,
        window_count: int = 1,
    ) -> None:
        if not messages:
            return

        message_by_id = {message.message_id: message for message in messages}
        handled_message_ids: set[str] = set()
        if settings.feishu_import_debug_logging:
            logger.info(
                "正在分析第 %s/%s 组，共 %s 条消息：%s",
                window_index,
                window_count,
                len(messages),
                _window_preview(messages),
            )

        try:
            drafts = await self.deepseek_client.summarize_feishu_requirements(messages)
        except Exception as exc:  # noqa: BLE001 - per-window isolation for batch imports.
            detail = _error_detail(exc)
            if settings.feishu_import_debug_logging:
                if isinstance(exc, HTTPException) and exc.status_code == 502:
                    logger.info("DeepSeek 返回格式无效：%s", detail)
                else:
                    logger.info("DeepSeek 分析失败：%s", detail)
            for message in messages:
                self._record(message, "failed", raw_text=message.text.strip(), error=detail)
                stats.add("failed")
            return
        if settings.feishu_import_debug_logging:
            if drafts:
                logger.info("DeepSeek 分析完成：识别到 %s 个需求（%s）", len(drafts), _drafts_preview(drafts))
            else:
                logger.info("DeepSeek 分析完成：模型未识别到需求")

        for draft in drafts:
            source_messages = [
                message_by_id[message_id]
                for message_id in draft.source_message_ids
                if message_id in message_by_id and message_id not in handled_message_ids
            ]
            if not source_messages:
                source_messages = [
                    message
                    for message in messages
                    if message.message_id not in handled_message_ids
                ]
            if not source_messages:
                continue

            if draft.confidence < settings.feishu_import_min_confidence:
                if settings.feishu_import_debug_logging:
                    logger.info(
                        "跳过低置信度需求：%s（置信度 %.2f）",
                        draft.title,
                        draft.confidence,
                    )
                for message in source_messages:
                    self._record(message, "skipped", raw_text=message.text.strip())
                    handled_message_ids.add(message.message_id)
                    stats.add("skipped")
                    stats.add("low_confidence_skipped")
                continue

            try:
                await self._apply_draft(draft.title, draft.description, source_messages, stats)
            except Exception as exc:  # noqa: BLE001 - keep remaining drafts isolated.
                detail = _error_detail(exc)
                for message in source_messages:
                    self._record(message, "failed", raw_text=message.text.strip(), error=detail)
                    stats.add("failed")
            handled_message_ids.update(message.message_id for message in source_messages)

        for message in messages:
            if message.message_id in handled_message_ids:
                continue
            self._record(message, "skipped", raw_text=message.text.strip())
            stats.add("skipped")

    async def _process_message(self, message: FeishuChatMessage, stats: FeishuImportRunResponse) -> None:
        cleaned_text = message.text.strip()
        if self._is_definitely_invalid(message, cleaned_text):
            self._record(message, "skipped", raw_text=cleaned_text)
            stats.add("skipped")
            return

        try:
            draft = await self.deepseek_client.draft_suggestion(cleaned_text)
            await self._apply_draft(draft.title, draft.description, [message], stats)
        except Exception as exc:  # noqa: BLE001 - per-message isolation for batch imports.
            detail = _error_detail(exc)
            self._record(message, "failed", raw_text=cleaned_text, error=detail)
            stats.add("failed")

    async def _apply_draft(
        self,
        title: str,
        description: str,
        source_messages: list[FeishuChatMessage],
        stats: FeishuImportRunResponse,
    ) -> None:
        similar = await SimilarRequirementsService(self.repository).find_similar(
            SimilarRequirementsRequest(
                title=title,
                description=description,
                limit=1,
            )
        )
        duplicate = (
            similar.items[0]
            if similar.items and similar.items[0].similarity >= settings.feishu_import_duplicate_threshold
            else None
        )
        if duplicate is not None:
            for message in source_messages:
                user = self.repository.ensure_feishu_user(message.sender_open_id, message.sender_name)
                try:
                    self.repository.create_vote(duplicate.id, user)
                except IntegrityError:
                    self._record(message, "already_voted", raw_text=message.text.strip(), post_id=duplicate.id)
                    stats.add("already_voted")
                    continue
                self._record(message, "voted", raw_text=message.text.strip(), post_id=duplicate.id)
                stats.add("voted")
            stats.add("generated_requirements")
            stats.add("grouped_messages", len(source_messages))
            return

        creator_message = source_messages[0]
        creator = self.repository.ensure_feishu_user(creator_message.sender_open_id, creator_message.sender_name)
        post = self.repository.create_post(
            PostCreate(
                title=title,
                description=description,
                tags=settings.feishu_import_default_tags,
            ),
            creator,
        )
        for message in source_messages:
            self._record(message, "created", raw_text=message.text.strip(), post_id=post.id)
        stats.add("created")
        stats.add("generated_requirements")
        stats.add("grouped_messages", len(source_messages))
        stats.add_created_title(post.title)

    def _is_definitely_invalid(self, message: FeishuChatMessage, cleaned_text: str) -> bool:
        if not cleaned_text:
            if settings.feishu_import_debug_logging:
                logger.info("过滤空消息")
            return True
        if cleaned_text.casefold() == "this message was recalled":
            if settings.feishu_import_debug_logging:
                logger.info("过滤已撤回消息")
            return True
        sender_type = (message.sender_type or "").lower()
        is_featurevote_summary = (
            sender_type in {"app", "bot"}
            and cleaned_text.startswith("FeatureVote 需求导入已完成")
        )
        if is_featurevote_summary:
            if settings.feishu_import_debug_logging:
                logger.info("过滤 FeatureVote 导入摘要")
            return True
        return False

    def _record(
        self,
        message: FeishuChatMessage,
        status: str,
        *,
        raw_text: str,
        post_id: str | None = None,
        error: str | None = None,
    ) -> None:
        self.repository.record_feishu_import(
            message_id=message.message_id,
            chat_id=message.chat_id,
            sender_open_id=message.sender_open_id,
            sender_name=message.sender_name,
            raw_text=raw_text,
            status=status,
            post_id=post_id,
            error=error,
        )

    def _notify_chat(self, chat_id: str, stats: FeishuImportRunResponse) -> None:
        if not settings.feishu_import_notify_chat:
            return
        if stats.created + stats.voted + stats.already_voted + stats.failed <= 0:
            return
        try:
            self.feishu_client.send_chat_text_message(chat_id, _format_chat_summary(stats))
        except Exception as exc:  # noqa: BLE001 - notification failure must not fail import.
            logger.warning("发送飞书导入摘要失败：%s", exc)


def _error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


def _snapshot(stats: FeishuImportRunResponse) -> FeishuImportRunResponse:
    return FeishuImportRunResponse(
        fetched=stats.fetched,
        skipped=stats.skipped,
        created=stats.created,
        voted=stats.voted,
        already_voted=stats.already_voted,
        failed=stats.failed,
        windows_processed=stats.windows_processed,
        generated_requirements=stats.generated_requirements,
        grouped_messages=stats.grouped_messages,
        low_confidence_skipped=stats.low_confidence_skipped,
        created_titles=list(stats.created_titles),
    )


def _delta(before: FeishuImportRunResponse, after: FeishuImportRunResponse) -> FeishuImportRunResponse:
    return FeishuImportRunResponse(
        fetched=after.fetched - before.fetched,
        skipped=after.skipped - before.skipped,
        created=after.created - before.created,
        voted=after.voted - before.voted,
        already_voted=after.already_voted - before.already_voted,
        failed=after.failed - before.failed,
        windows_processed=after.windows_processed - before.windows_processed,
        generated_requirements=after.generated_requirements - before.generated_requirements,
        grouped_messages=after.grouped_messages - before.grouped_messages,
        low_confidence_skipped=after.low_confidence_skipped - before.low_confidence_skipped,
        created_titles=after.created_titles[len(before.created_titles):],
    )


def _format_chat_summary(stats: FeishuImportRunResponse) -> str:
    lines = [
        "FeatureVote 需求导入已完成",
        f"读取消息：{stats.fetched}",
        f"新增需求：{stats.created}",
        f"重复需求加票：{stats.voted}",
        f"已投过票：{stats.already_voted}",
    ]
    if stats.failed:
        lines.append(f"处理失败：{stats.failed}")
    if stats.created_titles:
        lines.append("新增需求标题：")
        max_titles = 5
        for title in stats.created_titles[:max_titles]:
            lines.append(f"- {title}")
        remaining = len(stats.created_titles) - max_titles
        if remaining > 0:
            lines.append(f"...还有 {remaining} 个新增需求")
    return "\n".join(lines)


def _message_windows(messages: list[FeishuChatMessage]) -> list[list[FeishuChatMessage]]:
    timed_messages = [message for message in messages if message.sent_at is not None]
    untimed_messages = [message for message in messages if message.sent_at is None]
    timed_messages.sort(key=lambda message: message.sent_at)

    max_messages = max(1, settings.feishu_import_max_messages_per_summary)
    duration = timedelta(minutes=max(1, settings.feishu_import_window_minutes))
    windows: list[list[FeishuChatMessage]] = []
    current: list[FeishuChatMessage] = []
    window_start = None

    for message in timed_messages:
        if not current:
            current = [message]
            window_start = message.sent_at
            continue
        if window_start is not None and (
            message.sent_at - window_start >= duration or len(current) >= max_messages
        ):
            windows.append(current)
            current = [message]
            window_start = message.sent_at
        else:
            current.append(message)
    if current:
        windows.append(current)

    for index in range(0, len(untimed_messages), max_messages):
        windows.append(untimed_messages[index:index + max_messages])
    return windows


def _window_preview(messages: list[FeishuChatMessage]) -> str:
    return "；".join(_content_preview(message.text) for message in messages)


def _drafts_preview(drafts) -> str:
    return "；".join(f"{draft.title}，置信度 {draft.confidence:.2f}" for draft in drafts)


def _content_preview(text: str, max_chars: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}…"
