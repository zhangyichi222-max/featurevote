import pytest
from fastapi import HTTPException

from app.clients.deepseek import (
    DeepSeekSuggestionClient,
    _normalize_description,
    _parse_suggestion_draft,
)


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
        "期望结果：请描述这个需求完成后应达到的效果。"
    )


def test_parse_suggestion_draft_rejects_invalid_content() -> None:
    try:
        _parse_suggestion_draft("not json")
    except HTTPException as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("Expected invalid AI content to raise HTTPException.")


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
