from __future__ import annotations

import logging
import re
from datetime import timedelta

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
        remaining = max(1, settings.feishu_import_batch_size)
        fetched_messages: list[FeishuChatMessage] = []
        while remaining > 0:
            page_size = min(remaining, 50)
            messages, page_token = self.feishu_client.list_chat_text_messages(
                chat_id,
                page_size=page_size,
                page_token=page_token,
            )
            output.add("fetched", len(messages))
            fetched_messages.extend(messages)
            remaining -= page_size
            if not page_token:
                break
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
        duplicate_skipped = 0
        filtered_skipped = 0
        for message in messages:
            if self.repository.get_imported_feishu_message(message.message_id) is not None:
                stats.add("skipped")
                duplicate_skipped += 1
                continue

            cleaned_text = message.text.strip()
            if self._should_skip(message, cleaned_text):
                self._record(message, "skipped", raw_text=cleaned_text)
                stats.add("skipped")
                filtered_skipped += 1
                continue
            eligible.append(message)

        windows = _message_windows(eligible)
        if settings.feishu_import_debug_logging:
            logger.info(
                "Feishu import grouping prepared: fetched=%s duplicate_skipped=%s filtered_skipped=%s eligible=%s windows=%s",
                len(messages),
                duplicate_skipped,
                filtered_skipped,
                len(eligible),
                len(windows),
            )
        for window in windows:
            stats.add("windows_processed")
            await self._process_message_window(window, stats)

    async def _process_message_window(
        self,
        messages: list[FeishuChatMessage],
        stats: FeishuImportRunResponse,
    ) -> None:
        if not messages:
            return

        message_by_id = {message.message_id: message for message in messages}
        handled_message_ids: set[str] = set()
        if settings.feishu_import_debug_logging:
            logger.info(
                "Feishu import processing window: message_count=%s message_ids=%s preview=%s",
                len(messages),
                ",".join(message_by_id),
                _window_preview(messages),
            )

        try:
            drafts = await self.deepseek_client.summarize_feishu_requirements(messages)
        except Exception as exc:  # noqa: BLE001 - per-window isolation for batch imports.
            detail = _error_detail(exc)
            if settings.feishu_import_debug_logging:
                logger.info(
                    "Feishu import window failed: message_ids=%s error=%s",
                    ",".join(message_by_id),
                    detail,
                )
            for message in messages:
                self._record(message, "failed", raw_text=message.text.strip(), error=detail)
                stats.add("failed")
            return
        if settings.feishu_import_debug_logging:
            logger.info(
                "Feishu import parsed window drafts: message_ids=%s draft_count=%s drafts=%s",
                ",".join(message_by_id),
                len(drafts),
                _drafts_preview(drafts),
            )

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
                        "Feishu import skipped low-confidence draft: title=%s confidence=%.3f source_message_ids=%s",
                        draft.title,
                        draft.confidence,
                        ",".join(message.message_id for message in source_messages),
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
            if settings.feishu_import_debug_logging:
                logger.info(
                    "Feishu import skipped unassigned window message: message_id=%s text=%s",
                    message.message_id,
                    _truncate_debug_text(message.text.strip()),
                )
            self._record(message, "skipped", raw_text=message.text.strip())
            stats.add("skipped")

    async def _process_message(self, message: FeishuChatMessage, stats: FeishuImportRunResponse) -> None:
        if self.repository.get_imported_feishu_message(message.message_id) is not None:
            stats.add("skipped")
            return

        cleaned_text = message.text.strip()
        if self._should_skip(message, cleaned_text):
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

    def _should_skip(self, message: FeishuChatMessage, cleaned_text: str) -> bool:
        if len(cleaned_text) < settings.feishu_import_min_text_chars:
            if settings.feishu_import_debug_logging:
                logger.info(
                    "Feishu import pre-filter skipped short message: message_id=%s chars=%s text=%s",
                    message.message_id,
                    len(cleaned_text),
                    _truncate_debug_text(cleaned_text),
                )
            return True
        sender_type = (message.sender_type or "").lower()
        if sender_type in {"app", "bot"}:
            if settings.feishu_import_debug_logging:
                logger.info(
                    "Feishu import pre-filter skipped sender message: message_id=%s sender_type=%s text=%s",
                    message.message_id,
                    sender_type,
                    _truncate_debug_text(cleaned_text),
                )
            return True
        skipped = _looks_like_non_requirement(cleaned_text)
        if skipped and settings.feishu_import_debug_logging:
            logger.info(
                "Feishu import pre-filter skipped non-requirement message: message_id=%s text=%s",
                message.message_id,
                _truncate_debug_text(cleaned_text),
            )
        return skipped

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
            logger.warning("Failed to send Feishu import summary to chat %s: %s", chat_id, exc)


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
    lines = []
    for message in messages:
        sent_at = message.sent_at.isoformat() if message.sent_at else "unknown-time"
        text = message.text.strip().replace("\r", " ").replace("\n", " ")
        lines.append(f"{message.message_id}@{sent_at}: {text}")
    return _truncate_debug_text(" | ".join(lines))


def _drafts_preview(drafts) -> str:
    parts = []
    for draft in drafts:
        parts.append(
            f"title={draft.title!r}, confidence={draft.confidence:.3f}, "
            f"source_message_ids={','.join(draft.source_message_ids)}"
        )
    return _truncate_debug_text(" | ".join(parts) if parts else "<none>")


def _truncate_debug_text(text: str) -> str:
    max_chars = max(200, settings.feishu_import_debug_log_max_chars)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [truncated {len(text) - max_chars} chars]"


def _looks_like_non_requirement(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True

    lower = cleaned.lower()
    requirement_markers = (
        "需要",
        "希望",
        "能不能",
        "是否可以",
        "问题",
        "需求",
        "优化",
        "支持",
        "增加",
        "改进",
        "want",
        "need",
        "please",
        "should",
    )
    if any(marker in lower for marker in requirement_markers):
        return False

    command_pattern = (
        r"^\s*(python|pip|npm|pnpm|yarn|node|git|docker|kubectl|helm|bash|sh|cd|ls|cat|tail|grep|"
        r"systemctl|journalctl)\b"
    )
    if re.match(command_pattern, lower):
        return True

    log_patterns = (
        r"\b(traceback|exception|error|warn|info|debug)\b.*\b(line|at|in)\b",
        r"^\s*\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}",
        r"^\s*(ok|done|success|failed|pass|passed|warning|error)[:\s]",
    )
    if any(re.search(pattern, lower) for pattern in log_patterns):
        return True

    code_or_log_chars = sum(cleaned.count(char) for char in "{}[]();=|")
    return code_or_log_chars >= 6 and len(cleaned) < 240
