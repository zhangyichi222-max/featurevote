import pytest
from fastapi import HTTPException

from app.clients.deepseek import (
    DeepSeekSuggestionClient,
    _normalize_description,
    _parse_suggestion_draft,
)


def test_parse_suggestion_draft_accepts_json_content() -> None:
    draft = _parse_suggestion_draft(
        '{"title":"Export vote results by department",'
        '"description":"Problem: Admins cannot export vote totals.\\n\\n'
        'Context: Reports are prepared manually today.\\n\\n'
        'Expected result: Admins can download a CSV grouped by department."}'
    )

    assert draft.title == "Export vote results by department"
    assert "Problem:" in draft.description
    assert "Context:" in draft.description
    assert "Expected result:" in draft.description


def test_parse_suggestion_draft_extracts_json_from_wrapped_content() -> None:
    draft = _parse_suggestion_draft(
        'Here is JSON: {"title":"Cleaner export flow","description":"Need easier exports."}'
    )

    assert draft.title == "Cleaner export flow"
    assert "Problem:" in draft.description
    assert "Context:" in draft.description
    assert "Expected result:" in draft.description


def test_normalize_description_keeps_exact_three_sections() -> None:
    description = _normalize_description(
        "Problem: Admins cannot export vote totals.\n\n"
        "Context: Reports are prepared manually today.\n\n"
        "Expected result: Admins can download a CSV grouped by department."
    )

    assert description == (
        "Problem: Admins cannot export vote totals.\n\n"
        "Context: Reports are prepared manually today.\n\n"
        "Expected result: Admins can download a CSV grouped by department."
    )


def test_normalize_description_rejects_extra_sections() -> None:
    description = _normalize_description(
        "Problem: Admins cannot export vote totals.\n\n"
        "Context: Reports are prepared manually today.\n\n"
        "Expected result: Admins can download a CSV grouped by department.\n\n"
        "Owner: Analytics team"
    )

    assert description == (
        "Problem: Admins cannot export vote totals. Reports are prepared manually today. "
        "Admins can download a CSV grouped by department. Analytics team\n\n"
        "Context: Add relevant users, workflow, and timing details.\n\n"
        "Expected result: Describe the outcome that would make this request successful."
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
