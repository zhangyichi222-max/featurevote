import pytest
import logging
from fastapi import HTTPException

from app.clients.deepseek import (
    DeepSeekSuggestionClient,
    _normalize_description,
    _parse_feishu_requirement_drafts,
    _parse_suggestion_draft,
)
from app.clients.feishu import FeishuChatMessage
from app.core.config import settings


def test_parse_suggestion_draft_accepts_json_content() -> None:
    draft = _parse_suggestion_draft(
        '{"title":"按部门导出投票结果",'
        '"description":"问题：管理员无法导出投票总数。\\n\\n'
        '场景：复盘会议需要人工整理报表。\\n\\n'
        '期望结果：管理员可以下载按部门分组的 CSV。"}'
    )

    assert draft.title == "按部门导出投票结果"
    assert "问题：" in draft.description
    assert "场景：" in draft.description
    assert "期望结果：" in draft.description


def test_parse_suggestion_draft_extracts_json_from_wrapped_content() -> None:
    draft = _parse_suggestion_draft(
        'Here is JSON: {"title":"优化导出流程","description":"需要更方便地导出数据。"}'
    )

    assert draft.title == "优化导出流程"
    assert "问题：" in draft.description
    assert "场景：" in draft.description
    assert "期望结果：" in draft.description


def test_normalize_description_keeps_exact_three_sections() -> None:
    description = _normalize_description(
        "问题：管理员无法导出投票总数。\n\n"
        "场景：复盘会议需要人工整理报表。\n\n"
        "期望结果：管理员可以下载按部门分组的 CSV。"
    )

    assert description == (
        "问题：管理员无法导出投票总数。\n\n"
        "场景：复盘会议需要人工整理报表。\n\n"
        "期望结果：管理员可以下载按部门分组的 CSV。"
    )


def test_normalize_description_rejects_extra_sections() -> None:
    description = _normalize_description(
        "问题：管理员无法导出投票总数。\n\n"
        "场景：复盘会议需要人工整理报表。\n\n"
        "期望结果：管理员可以下载按部门分组的 CSV。\n\n"
        "负责人：分析团队"
    )

    assert description == (
        "问题：管理员无法导出投票总数。 复盘会议需要人工整理报表。 "
        "管理员可以下载按部门分组的 CSV。 分析团队\n\n"
        "场景：请补充相关用户、操作流程和发生时机。\n\n"
        "期望结果：请描述这份需求草稿被采纳并完成后应达到的效果。"
    )


def test_parse_suggestion_draft_rejects_invalid_content() -> None:
    try:
        _parse_suggestion_draft("not json")
    except HTTPException as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("Expected invalid AI content to raise HTTPException.")


def test_parse_feishu_requirement_drafts_accepts_grouped_json() -> None:
    drafts = _parse_feishu_requirement_drafts(
        '{"requirements":[{"title":"一键部署测试环境",'
        '"description":"问题：测试部署依赖手动步骤。\\n\\n场景：开发完成后需要验证。\\n\\n期望结果：一键部署到测试环境。",'
        '"source_message_ids":["om_1","om_2"],"confidence":0.87}]}'
    )

    assert len(drafts) == 1
    assert drafts[0].title == "一键部署测试环境"
    assert drafts[0].source_message_ids == ["om_1", "om_2"]
    assert drafts[0].confidence == 0.87


def test_parse_feishu_requirement_drafts_returns_empty_for_model_empty_result() -> None:
    assert _parse_feishu_requirement_drafts('{"requirements":[]}') == []


def test_parse_feishu_requirement_drafts_rejects_invalid_candidates() -> None:
    with pytest.raises(HTTPException) as exc:
        _parse_feishu_requirement_drafts(
            '{"requirements":[{"title":"短","description":"","source_message_ids":[],"confidence":0.8}]}'
        )

    assert exc.value.status_code == 502
    assert "返回 1 个候选需求" in str(exc.value.detail)
    assert "格式无效" in str(exc.value.detail)


@pytest.mark.anyio
async def test_feishu_summary_prompt_requires_full_conversation_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DeepSeekSuggestionClient()
    captured = {}

    async def fake_chat(messages, *, service_name):
        captured["messages"] = messages
        captured["service_name"] = service_name
        return (
            '{"requirements":[{"title":"从群组历史消息创建任务",'
            '"description":"问题：无法确认历史消息能否创建任务。\\n\\n'
            '场景：验证历史消息导入。\\n\\n'
            '期望结果：可以从群组历史消息创建任务。",'
            '"source_message_ids":["om_test"],"confidence":0.9}]}'
        )

    monkeypatch.setattr(settings, "deepseek_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(client, "_chat", fake_chat)
    message = FeishuChatMessage(
        message_id="om_test",
        chat_id="oc_test",
        sender_open_id="ou_test",
        sender_name="测试用户",
        sender_type="user",
        text="生成一个测试需求，功能为能否正常从群组历史消息中创建对应的任务",
        sent_at=None,
    )

    drafts = await client.summarize_feishu_requirements([message])

    system_prompt = captured["messages"][0]["content"]
    user_prompt = captured["messages"][1]["content"]
    assert "综合整个对话窗口理解上下文" in system_prompt
    assert "短句" in system_prompt
    assert "生成一个需求" in system_prompt
    assert "候选需求草稿" in system_prompt
    assert message.text in user_prompt
    assert drafts[0].title == "从群组历史消息创建任务"


async def _fake_post_non_json(url: str, json: dict, headers: dict):
    _ = url, json, headers
    return _FakeResponse(json_error=ValueError("not json"))


async def _fake_post_list_json(url: str, json: dict, headers: dict):
    _ = url, json, headers
    return _FakeResponse(payload=[])


@pytest.mark.anyio
async def test_deepseek_chat_maps_non_json_success_to_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clients.deepseek.httpx.AsyncClient", lambda timeout: _FakeAsyncClient(_fake_post_non_json))

    with pytest.raises(HTTPException) as exc:
        await DeepSeekSuggestionClient()._chat(
            [{"role": "user", "content": "Need a clearer export flow"}],
            service_name="AI drafting",
        )

    assert exc.value.status_code == 502


@pytest.mark.anyio
async def test_deepseek_chat_maps_non_object_success_to_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clients.deepseek.httpx.AsyncClient", lambda timeout: _FakeAsyncClient(_fake_post_list_json))

    with pytest.raises(HTTPException) as exc:
        await DeepSeekSuggestionClient()._chat(
            [{"role": "user", "content": "Need a clearer export flow"}],
            service_name="AI drafting",
        )

    assert exc.value.status_code == 502


@pytest.mark.anyio
async def test_feishu_parse_failure_logs_truncated_raw_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = DeepSeekSuggestionClient()
    raw_response = "无法解析的响应" + ("x" * 5000)

    async def fake_chat(messages, *, service_name):
        _ = messages, service_name
        return raw_response

    monkeypatch.setattr(settings, "deepseek_enabled", True)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "feishu_import_debug_logging", True)
    monkeypatch.setattr(settings, "feishu_import_debug_log_max_chars", 200)
    monkeypatch.setattr(client, "_chat", fake_chat)
    message = FeishuChatMessage(
        message_id="om_test",
        chat_id="oc_test",
        sender_open_id="ou_test",
        sender_name="测试用户",
        sender_type="user",
        text="希望支持按部门导出投票结果。",
        sent_at=None,
    )

    with caplog.at_level(logging.ERROR, logger="app.clients.deepseek"):
        with pytest.raises(HTTPException):
            await client.summarize_feishu_requirements([message])

    assert "DeepSeek 响应解析失败，原始响应：无法解析的响应" in caplog.text
    assert "truncated" in caplog.text
    assert raw_response not in caplog.text


class _FakeAsyncClient:
    def __init__(self, post):
        self._post = post

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url: str, json: dict, headers: dict):
        return await self._post(url, json, headers)


class _FakeResponse:
    def __init__(self, payload=None, json_error: Exception | None = None):
        self._payload = payload
        self._json_error = json_error

    def raise_for_status(self) -> None:
        return None

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload
