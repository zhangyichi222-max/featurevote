import pytest
from fastapi import HTTPException

from app.clients.ollama import OllamaSuggestionClient, _normalize_description, _parse_suggestion_draft


def test_parse_suggestion_draft_accepts_json_content() -> None:
    draft = _parse_suggestion_draft(
        '{"title":"支持按部门筛选投票结果",'
        '"description":"问题：无法区分部门需求。\\n\\n场景：管理者评估需求时需要部门视角。\\n\\n期望结果：可以按部门查看投票。"}'
    )

    assert draft.title == "支持按部门筛选投票结果"
    assert "问题：" in draft.description
    assert "场景：" in draft.description
    assert "期望结果：" in draft.description


def test_parse_suggestion_draft_extracts_json_from_wrapped_content() -> None:
    draft = _parse_suggestion_draft(
        '好的：{"title":"支持导出投票结果","description":"问题：当前无法导出。"}'
    )

    assert draft.title == "支持导出投票结果"
    assert "问题：" in draft.description
    assert "场景：" in draft.description
    assert "期望结果：" in draft.description


def test_normalize_description_keeps_exact_three_sections() -> None:
    description = _normalize_description("问题：无法导出。\n\n场景：复盘会议。\n\n期望结果：可以下载表格。")

    assert description == "问题：无法导出。\n\n场景：复盘会议。\n\n期望结果：可以下载表格。"


def test_normalize_description_rejects_extra_sections() -> None:
    description = _normalize_description(
        "问题：无法导出。\n\n场景：复盘会议。\n\n期望结果：可以下载表格。\n\n备注：尽快做。"
    )

    assert description == (
        "问题：无法导出。 复盘会议。 可以下载表格。 尽快做。"
        "\n\n场景：请补充这个需求出现的使用场景。"
        "\n\n期望结果：请补充希望产品达到的效果。"
    )


def test_parse_suggestion_draft_rejects_invalid_content() -> None:
    try:
        _parse_suggestion_draft("not json")
    except HTTPException as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("Expected invalid AI content to raise HTTPException.")


async def _fake_post_non_json(url: str, json: dict):
    _ = url, json
    return _FakeResponse(json_error=ValueError("not json"))


async def _fake_post_list_json(url: str, json: dict):
    _ = url, json
    return _FakeResponse(payload=[])


@pytest.mark.anyio
async def test_ollama_chat_maps_non_json_success_to_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clients.ollama.httpx.AsyncClient", lambda timeout: _FakeAsyncClient(_fake_post_non_json))

    with pytest.raises(HTTPException) as exc:
        await OllamaSuggestionClient()._chat("Need a clearer export flow")

    assert exc.value.status_code == 502


@pytest.mark.anyio
async def test_ollama_chat_maps_non_object_success_to_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clients.ollama.httpx.AsyncClient", lambda timeout: _FakeAsyncClient(_fake_post_list_json))

    with pytest.raises(HTTPException) as exc:
        await OllamaSuggestionClient()._chat("Need a clearer export flow")

    assert exc.value.status_code == 502


class _FakeAsyncClient:
    def __init__(self, post):
        self._post = post

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url: str, json: dict):
        return await self._post(url, json)


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
