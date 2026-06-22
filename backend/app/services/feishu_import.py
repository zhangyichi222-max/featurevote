from __future__ import annotations

import logging

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
        while remaining > 0:
            page_size = min(remaining, 50)
            messages, page_token = self.feishu_client.list_chat_text_messages(
                chat_id,
                page_size=page_size,
                page_token=page_token,
            )
            output.add("fetched", len(messages))
            for message in messages:
                await self._process_message(message, output)
            remaining -= page_size
            if not page_token:
                break
        self._notify_chat(chat_id, _delta(before, output))
        return output

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
            user = self.repository.ensure_feishu_user(message.sender_open_id, message.sender_name)
            draft = await self.deepseek_client.draft_suggestion(cleaned_text)
            similar = await SimilarRequirementsService(self.repository).find_similar(
                SimilarRequirementsRequest(
                    title=draft.title,
                    description=draft.description,
                    limit=1,
                )
            )
            duplicate = (
                similar.items[0]
                if similar.items and similar.items[0].similarity >= settings.feishu_import_duplicate_threshold
                else None
            )
            if duplicate is not None:
                try:
                    self.repository.create_vote(duplicate.id, user)
                except IntegrityError:
                    self._record(message, "already_voted", raw_text=cleaned_text, post_id=duplicate.id)
                    stats.add("already_voted")
                    return
                self._record(message, "voted", raw_text=cleaned_text, post_id=duplicate.id)
                stats.add("voted")
                return

            post = self.repository.create_post(
                PostCreate(
                    title=draft.title,
                    description=draft.description,
                    tags=settings.feishu_import_default_tags,
                ),
                user,
            )
            self._record(message, "created", raw_text=cleaned_text, post_id=post.id)
            stats.add("created")
            stats.add_created_title(post.title)
        except Exception as exc:  # noqa: BLE001 - per-message isolation for batch imports.
            detail = _error_detail(exc)
            self._record(message, "failed", raw_text=cleaned_text, error=detail)
            stats.add("failed")

    def _should_skip(self, message: FeishuChatMessage, cleaned_text: str) -> bool:
        if len(cleaned_text) < settings.feishu_import_min_text_chars:
            return True
        sender_type = (message.sender_type or "").lower()
        return sender_type in {"app", "bot"}

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
