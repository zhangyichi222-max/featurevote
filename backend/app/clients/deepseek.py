import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai import SimilarRequirementItem, SuggestionDraftResponse
from app.schemas.task import FeishuMessageEvidence, FeishuTaskCandidate


SECTION_HEADINGS = ("问题：", "场景：", "期望结果：")


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

    async def draft_feishu_task_candidates(self, messages: list[dict[str, str]]) -> list[FeishuTaskCandidate]:
        if not settings.deepseek_enabled or not settings.deepseek_api_key or not messages:
            return []

        message_text = json.dumps(messages[:80], ensure_ascii=False)
        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你负责从飞书聊天记录中提取候选开发任务。只返回严格 JSON。"
                        "不要推断负责人、标签、状态、优先级或截止时间。"
                        "只输出明确可行动的任务；闲聊和系统消息忽略。"
                        "招聘、简历、候选人评估、面试、人才筛选、岗位匹配内容必须忽略。"
                        "格式："
                        '{"candidates":[{"message_id":"string","title":"3-160 chars","description_markdown":"markdown"}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"消息列表：{message_text}",
                },
            ],
            service_name="Feishu task import",
        )
        return _parse_feishu_task_candidates(content, messages)

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
                detail=f"{service_name} service is unavailable.",
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


def _parse_feishu_task_candidates(content: str, messages: list[dict[str, str]]) -> list[FeishuTaskCandidate]:
    payload = _load_json_object(content)
    raw_candidates = payload.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []

    by_message_id = {item.get("message_id", ""): item for item in messages}
    candidates: list[FeishuTaskCandidate] = []
    for index, item in enumerate(raw_candidates[:20]):
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("message_id", "")).strip()
        source = by_message_id.get(message_id, {})
        evidence = FeishuMessageEvidence(
            conversation_id=source.get("conversation_id", ""),
            conversation_title=source.get("conversation_title", ""),
            message_id=message_id or f"ai-{index}",
            sender_name=source.get("sender_name", ""),
            created_at=source.get("created_at", ""),
            content=source.get("content", "")[:1200],
        )
        try:
            candidates.append(
                FeishuTaskCandidate(
                    candidate_id=f"ai-{index}-{message_id or 'candidate'}"[:80],
                    title=str(item.get("title", "")).strip(),
                    description_markdown=str(item.get("description_markdown", "")).strip(),
                    evidence=[evidence] if evidence.content else [],
                )
            )
        except ValidationError:
            continue
    return candidates
