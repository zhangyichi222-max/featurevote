from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from fastapi import HTTPException, status

from app.schemas.task import FeishuMessageEvidence, FeishuTaskCandidate


ACTION_KEYWORDS = (
    "处理",
    "跟进",
    "修复",
    "排查",
    "回复",
    "确认",
    "支持",
    "补充",
    "实现",
    "优化",
    "整理",
    "导出",
    "帮忙",
    "需要",
    "麻烦",
    "todo",
    "fix",
    "follow",
    "support",
)
NON_TASK_KEYWORDS = (
    "候选人",
    "候选人评估",
    "招聘",
    "应聘",
    "面试",
    "简历",
    "岗位",
    "综合评价",
    "总评价",
    "评分",
    "候选人姓名",
    "工作年限",
    "薪资",
    "猎头",
    "人才",
    "入职",
    "offer",
    "resume",
    "candidate",
    "interview",
    "recruit",
)
MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_JSONL_BYTES = 20 * 1024 * 1024
MAX_CONVERSATIONS = 200
MAX_MESSAGES = 5000


@dataclass(frozen=True)
class ParsedFeishuMessage:
    conversation_id: str
    conversation_title: str
    message_id: str
    sender_name: str
    created_at: str
    content: str


@dataclass(frozen=True)
class ParsedFeishuImport:
    messages: list[ParsedFeishuMessage]
    conversations_count: int
    skipped_messages_count: int


def parse_feishu_export(content: bytes, filename: str) -> ParsedFeishuImport:
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import file is required.")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Import file is too large.")

    normalized_name = filename.lower()
    if normalized_name.endswith(".zip") or _looks_like_zip(content):
        jsonl = _read_jsonl_from_zip(content)
    else:
        jsonl = _decode_text(content)

    return _parse_jsonl(jsonl)


def generate_rule_based_candidates(import_data: ParsedFeishuImport, limit: int = 20) -> list[FeishuTaskCandidate]:
    candidates: list[FeishuTaskCandidate] = []
    seen_titles: set[str] = set()
    for message in import_data.messages:
        if not is_task_import_message(message.content, message.conversation_title):
            continue

        title = _build_title(message.content)
        normalized_title = title.casefold()
        if normalized_title in seen_titles:
            continue
        seen_titles.add(normalized_title)

        evidence = FeishuMessageEvidence(
            conversation_id=message.conversation_id,
            conversation_title=message.conversation_title,
            message_id=message.message_id,
            sender_name=message.sender_name,
            created_at=message.created_at,
            content=_truncate(message.content, 1200),
        )
        description = _build_description(message, evidence)
        candidates.append(
            FeishuTaskCandidate(
                candidate_id=_candidate_id(message),
                title=title,
                description_markdown=description,
                evidence=[evidence],
            )
        )
        if len(candidates) >= limit:
            break

    return candidates


def is_task_import_message(content: str, conversation_title: str = "") -> bool:
    combined = f"{conversation_title} {content}".casefold()
    if any(keyword.casefold() in combined for keyword in NON_TASK_KEYWORDS):
        return False
    return _looks_actionable(content)


def append_evidence_section(description: str, evidence: list[FeishuMessageEvidence]) -> str:
    if not evidence:
        return description
    lines = ["", "", "## 来源消息证据"]
    for item in evidence[:5]:
        prefix = f"- {item.conversation_title or item.conversation_id}"
        if item.sender_name:
            prefix += f" / {item.sender_name}"
        if item.created_at:
            prefix += f" / {item.created_at}"
        lines.append(prefix)
        lines.append(f"  > {_single_line(item.content)}")
    return f"{description.rstrip()}{chr(10).join(lines)}"


def _read_jsonl_from_zip(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            candidates = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.replace("\\", "/").endswith("conversation-logs.jsonl")
            ]
            if not candidates:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="conversation-logs.jsonl not found in zip.",
                )
            if candidates[0].file_size > MAX_JSONL_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="conversation-logs.jsonl is too large.",
                )
            with archive.open(candidates[0]) as stream:
                return _decode_text(stream.read())
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid zip file.") from exc


def _parse_jsonl(text: str) -> ParsedFeishuImport:
    messages: list[ParsedFeishuMessage] = []
    conversations_count = 0
    skipped_messages_count = 0

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSONL at line {line_number}.",
            ) from exc
        if not isinstance(record, dict):
            skipped_messages_count += 1
            continue

        conversations_count += 1
        if conversations_count > MAX_CONVERSATIONS:
            break
        conversation_id = _string_value(record.get("sourceId") or record.get("id"))
        conversation_title = _string_value(record.get("sourceTitle"))
        raw_messages = record.get("messages")
        if not isinstance(raw_messages, list):
            continue

        for raw_message in raw_messages:
            if len(messages) >= MAX_MESSAGES:
                break
            if (
                not isinstance(raw_message, dict)
                or raw_message.get("deleted")
                or raw_message.get("msg_type") in {"system", "image", "file", "media", "audio", "video", "sticker"}
            ):
                skipped_messages_count += 1
                continue
            content = _extract_content(raw_message.get("content"))
            if not content:
                skipped_messages_count += 1
                continue
            sender = raw_message.get("sender")
            messages.append(
                ParsedFeishuMessage(
                    conversation_id=_truncate(conversation_id, 120),
                    conversation_title=_truncate(conversation_title, 240),
                    message_id=_truncate(_string_value(raw_message.get("message_id")), 120),
                    sender_name=_truncate(_sender_name(sender), 120),
                    created_at=_truncate(_string_value(raw_message.get("create_time")), 80),
                    content=content,
                )
            )

    if not conversations_count:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No conversations found in import file.")
    return ParsedFeishuImport(
        messages=messages,
        conversations_count=conversations_count,
        skipped_messages_count=skipped_messages_count,
    )


def _extract_content(value: Any) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return _normalize_text(stripped)
            return _extract_content(parsed)
        return _normalize_text(stripped)
    if isinstance(value, dict):
        for key in ("text", "content", "title"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return _normalize_text(text)
    return ""


def _sender_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return _string_value(value.get("name") or value.get("id"))


def _build_title(content: str) -> str:
    text = re.sub(r"\s+", " ", content).strip()
    text = re.sub(r"^(麻烦|请|帮忙|需要|帮我|我们需要|todo[:：]?)", "", text, flags=re.IGNORECASE).strip()
    title = _truncate(text, 80)
    if len(title) < 3:
        title = f"跟进飞书消息：{title}"
    return title[:160]


def _build_description(message: ParsedFeishuMessage, evidence: FeishuMessageEvidence) -> str:
    parts = [
        "根据飞书对话生成的候选任务，请在创建前确认范围和表述。",
        "",
        f"来源会话：{message.conversation_title or message.conversation_id}",
    ]
    if message.sender_name:
        parts.append(f"发送人：{message.sender_name}")
    if message.created_at:
        parts.append(f"消息时间：{message.created_at}")
    parts.extend(["", "证据：", f"> {_single_line(evidence.content)}"])
    return "\n".join(parts)


def _candidate_id(message: ParsedFeishuMessage) -> str:
    raw = "|".join([message.conversation_id, message.message_id, message.content])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _looks_actionable(content: str) -> bool:
    lowered = content.casefold()
    return any(keyword.casefold() in lowered for keyword in ACTION_KEYWORDS)


def _looks_like_zip(content: bytes) -> bool:
    return content.startswith(b"PK\x03\x04")


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import file must be UTF-8 or GB18030 text.")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _string_value(value: Any) -> str:
    return "" if value is None else str(value).strip()
