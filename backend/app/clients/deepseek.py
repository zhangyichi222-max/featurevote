import json
import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.config import settings
from app.clients.feishu import FeishuChatMessage
from app.schemas.ai import FeishuRequirementDraft, SimilarRequirementItem, SuggestionDraftResponse


SECTION_HEADINGS = ("问题：", "场景：", "期望结果：")
logger = logging.getLogger(__name__)


class DeepSeekSuggestionClient:
    async def draft_suggestion(self, idea: str) -> SuggestionDraftResponse:
        if not settings.deepseek_enabled or not settings.deepseek_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI drafting is not enabled.",
            )

        cleaned_idea = idea.strip()
        if len(cleaned_idea) < settings.deepseek_min_text_chars:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Please enter at least {settings.deepseek_min_text_chars} characters for AI drafting.",
            )
        if len(cleaned_idea) > settings.deepseek_max_text_chars:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Please keep the idea under {settings.deepseek_max_text_chars} characters.",
            )

        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你负责把用户的零散产品反馈整理成清晰的需求草稿。"
                        "默认使用简体中文输出。只返回严格 JSON，字段必须是 title 和 description。"
                        "description 必须且只能包含三个段落，段落标题依次为：问题：、场景：、期望结果：。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请根据下面的原始想法生成需求草稿。\n\n"
                        f"原始想法：{cleaned_idea}\n\n"
                        "JSON 示例："
                        '{"title":"按部门导出投票结果",'
                        '"description":"问题：...\\n\\n场景：...\\n\\n期望结果：..."}'
                    ),
                },
            ],
            service_name="AI drafting",
        )
        return _parse_suggestion_draft(content)

    async def summarize_feishu_requirements(
        self,
        messages: list[FeishuChatMessage],
    ) -> list[FeishuRequirementDraft]:
        if not settings.deepseek_enabled or not settings.deepseek_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI drafting is not enabled.",
            )

        if not messages:
            return []

        window_text = _format_feishu_messages(messages)
        if len(window_text) > settings.deepseek_max_text_chars:
            window_text = window_text[: settings.deepseek_max_text_chars]

        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你负责把同一时间窗口内的飞书聊天记录归纳成产品反馈看板中的投票需求。"
                        "这些消息通常围绕同一个任务讨论，但也可能包含多个话题。"
                        "请优先提炼用户问题、业务目标和期望结果，不要把脚本名、命令名、日志、临时实现方案单独当成需求。"
                        "如果同一目标被多次讨论，只输出一个需求。"
                        "如果内容不是需求、信息不足或只是闲聊/日志/命令输出，不要输出需求。"
                        "默认使用简体中文。只返回严格 JSON，格式为："
                        '{"requirements":[{"title":"string","description":"问题：...\\n\\n场景：...\\n\\n期望结果：...",'
                        '"source_message_ids":["message_id"],"confidence":0.0}]}。'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请根据下面同一时间窗口内的飞书消息，按主题归纳出 0 到多个可投票需求。\n\n"
                        f"{window_text}"
                    ),
                },
            ],
            service_name="Feishu requirement summarization",
        )
        try:
            return _parse_feishu_requirement_drafts(content)
        except HTTPException:
            if settings.feishu_import_debug_logging:
                logger.error("DeepSeek 响应解析失败，原始响应：%s", _truncate_debug_text(content))
            raise

    async def assess_similar_requirements(
        self,
        title: str,
        description: str,
        candidates: list[SimilarRequirementItem],
    ) -> list[SimilarRequirementItem]:
        if not settings.deepseek_enabled or not settings.deepseek_api_key or not candidates:
            return candidates

        candidate_text = "\n".join(
            (
                f"- id: {candidate.id}\n"
                f"  title: {candidate.title}\n"
                f"  description: {candidate.description[:1200]}\n"
                f"  baseline_similarity: {candidate.similarity:.2f}"
            )
            for candidate in candidates
        )
        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You detect duplicate feature requests for a product feedback board. "
                        "Be conservative. Return strict JSON only: "
                        '{"results":[{"id":"string","confidence":0.0,"reason":"short reason"}]}. '
                        "Confidence is 0-1. High confidence means the new request and existing request ask for the same outcome."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"New request title: {title.strip()}\n"
                        f"New request description: {description.strip()[:2000]}\n\n"
                        f"Existing candidates:\n{candidate_text}"
                    ),
                },
            ],
            service_name="AI similarity",
        )
        return _parse_similarity_assessment(content, candidates)

    async def _chat(self, messages: list[dict[str, str]], *, service_name: str) -> str:
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": messages,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        if settings.deepseek_thinking == "enabled":
            payload["reasoning_effort"] = settings.deepseek_reasoning_effort

        try:
            async with httpx.AsyncClient(timeout=settings.deepseek_timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{service_name} 服务不可用。",
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{service_name} service returned an unreadable response.",
            ) from exc

        content = _extract_chat_content(data)
        if not content.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{service_name} service returned an empty response.",
            )
        return content


def _extract_chat_content(data: Any) -> str:
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an invalid response.",
        )

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an invalid response.",
        )

    first_choice = choices[0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an invalid response.",
        )
    return content


def _parse_suggestion_draft(content: str) -> SuggestionDraftResponse:
    payload = _load_json_object(content)
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    description = _normalize_description(description)

    try:
        return SuggestionDraftResponse(title=title, description=description)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI drafting service returned an invalid draft.",
        ) from exc


def _parse_feishu_requirement_drafts(content: str) -> list[FeishuRequirementDraft]:
    payload = _load_json_object(content)
    raw_requirements = payload.get("requirements", [])
    if not isinstance(raw_requirements, list):
        return []

    drafts: list[FeishuRequirementDraft] = []
    for item in raw_requirements:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        description = _normalize_description(str(item.get("description", "")).strip())
        raw_source_ids = item.get("source_message_ids", [])
        source_message_ids = [
            str(message_id).strip()
            for message_id in raw_source_ids
            if isinstance(message_id, str) and message_id.strip()
        ]
        confidence = item.get("confidence", 1.0)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0
        try:
            drafts.append(
                FeishuRequirementDraft(
                    title=title,
                    description=description,
                    source_message_ids=source_message_ids,
                    confidence=max(0.0, min(confidence_value, 1.0)),
                )
            )
        except ValidationError:
            continue
    return drafts


def _format_feishu_messages(messages: list[FeishuChatMessage]) -> str:
    lines = ["飞书消息："]
    for message in messages:
        sent_at = message.sent_at.isoformat() if message.sent_at else "unknown-time"
        sender = message.sender_name or message.sender_open_id or "unknown-sender"
        text = message.text.strip().replace("\r", " ").replace("\n", " ")
        lines.append(f"- id={message.message_id}; time={sent_at}; sender={sender}; text={text}")
    return "\n".join(lines)


def _truncate_debug_text(text: str) -> str:
    max_chars = max(200, settings.feishu_import_debug_log_max_chars)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [truncated {len(text) - max_chars} chars]"


def _load_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI drafting service returned an unreadable response.",
            ) from None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI drafting service returned an unreadable response.",
            ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI drafting service returned an invalid response.",
        )
    return parsed


def _normalize_description(description: str) -> str:
    parsed_sections = _extract_ordered_sections(description)
    if parsed_sections is not None:
        return "\n\n".join(f"{heading}{body}" for heading, body in parsed_sections)

    fallback_problem = _strip_extra_headings(description) or "请补充当前遇到的问题。"
    return "\n\n".join(
        [
            f"问题：{fallback_problem}",
            "场景：请补充相关用户、操作流程和发生时机。",
            "期望结果：请描述这个需求完成后应达到的效果。",
        ]
    )


def _extract_ordered_sections(description: str) -> list[tuple[str, str]] | None:
    pattern = re.compile(r"(问题：|场景：|期望结果：)")
    matches = list(pattern.finditer(description))
    headings = [match.group(1) for match in matches]
    if headings == list(SECTION_HEADINGS):
        output_headings = SECTION_HEADINGS
    else:
        return None

    parsed: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(description)
        body = description[start:end].strip()
        if not body or re.search(r"(^|\n)\s*([A-Za-z ]{1,32}:|[\u4e00-\u9fff]{1,16}：)", body):
            return None
        parsed.append((output_headings[index], body))

    prefix = description[: matches[0].start()].strip()
    return None if prefix else parsed


def _strip_extra_headings(text: str) -> str:
    cleaned = re.sub(r"(^|\n)\s*([A-Za-z ]{1,32}:|[\u4e00-\u9fff]{1,16}：)", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_similarity_assessment(
    content: str,
    candidates: list[SimilarRequirementItem],
) -> list[SimilarRequirementItem]:
    payload = _load_json_object(content)
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return candidates

    assessments: dict[str, tuple[float, str | None]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        confidence = item.get("confidence")
        reason = item.get("reason")
        if isinstance(item_id, str) and isinstance(confidence, (int, float)):
            assessments[item_id] = (
                max(0.0, min(float(confidence), 1.0)),
                str(reason).strip() if reason else None,
            )

    enhanced: list[SimilarRequirementItem] = []
    for candidate in candidates:
        confidence, reason = assessments.get(candidate.id, (candidate.similarity, candidate.reason))
        score = max(candidate.similarity, confidence)
        enhanced.append(
            candidate.model_copy(
                update={
                    "similarity": score,
                    "is_high_confidence": score >= 0.72,
                    "reason": reason or candidate.reason,
                }
            )
        )
    return sorted(enhanced, key=lambda item: item.similarity, reverse=True)
