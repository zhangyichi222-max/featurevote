import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai import SuggestionDraftResponse


class OllamaSuggestionClient:
    async def draft_suggestion(self, idea: str) -> SuggestionDraftResponse:
        if not settings.ollama_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI drafting is not enabled.",
            )

        cleaned_idea = idea.strip()
        if len(cleaned_idea) < settings.ollama_min_text_chars:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Please enter at least {settings.ollama_min_text_chars} characters for AI drafting.",
            )
        if len(cleaned_idea) > settings.ollama_max_text_chars:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Please keep the idea under {settings.ollama_max_text_chars} characters.",
            )

        content = await self._chat(cleaned_idea)
        return _parse_suggestion_draft(content)

    async def _chat(self, idea: str) -> str:
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个产品反馈写作助手。请把用户的一句话想法改写为需求投票系统里的清晰需求。"
                        "默认使用中文，内容务实、具体，不承诺实现方案，不夸大收益。"
                        "只返回 JSON，不要 Markdown。JSON 字段必须是 title 和 description。"
                        "description 只能包含三个段落，段落标题依次为：问题：、场景：、期望结果：。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请根据下面的粗略想法生成一个需求草稿。\n\n"
                        f"粗略想法：{idea}\n\n"
                        "返回格式示例："
                        '{"title":"支持按部门筛选投票结果",'
                        '"description":"问题：...\\n\\n场景：...\\n\\n期望结果：..."}'
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI drafting service is unavailable.",
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI drafting service returned an unreadable response.",
            ) from exc

        if not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI drafting service returned an invalid response.",
            )

        message = data.get("message")
        if not isinstance(message, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI drafting service returned an invalid response.",
            )

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI drafting service returned an empty response.",
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
    sections = ("问题：", "场景：", "期望结果：")
    parsed_sections = _extract_ordered_sections(description)
    if parsed_sections is not None:
        return "\n\n".join(f"{heading}{body}" for heading, body in parsed_sections)

    fallback_problem = _strip_extra_headings(description) or "请补充当前遇到的问题。"
    return "\n\n".join(
        [
            f"问题：{fallback_problem}",
            "场景：请补充这个需求出现的使用场景。",
            "期望结果：请补充希望产品达到的效果。",
        ]
    )


def _extract_ordered_sections(description: str) -> list[tuple[str, str]] | None:
    pattern = re.compile(r"(问题：|场景：|期望结果：)")
    matches = list(pattern.finditer(description))
    if [match.group(1) for match in matches] != ["问题：", "场景：", "期望结果："]:
        return None

    parsed: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(description)
        body = description[start:end].strip()
        if not body or re.search(r"(^|\n)\s*[^：:\n]{1,16}[：:]", body):
            return None
        parsed.append((match.group(1), body))

    prefix = description[: matches[0].start()].strip()
    return None if prefix else parsed


def _strip_extra_headings(text: str) -> str:
    cleaned = re.sub(r"(^|\n)\s*[^：:\n]{1,16}[：:]", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()
