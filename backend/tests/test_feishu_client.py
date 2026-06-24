from urllib import error
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.clients import feishu
from app.clients.feishu import FeishuClient, FeishuClientError


def test_feishu_http_error_includes_status_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_http_error(*args, **kwargs):
        raise error.HTTPError(
            url="https://open.feishu.cn/open-apis/im/v1/messages",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=_Body(b'{"code":99991663,"msg":"missing permission"}'),
        )

    monkeypatch.setattr(feishu.request, "urlopen", raise_http_error)

    with pytest.raises(FeishuClientError) as exc:
        FeishuClient()._request_json(feishu.request.Request("https://open.feishu.cn"))

    message = str(exc.value)
    assert "HTTP 400" in message
    assert "missing permission" in message


def test_feishu_url_error_includes_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_url_error(*args, **kwargs):
        raise error.URLError("timed out")

    monkeypatch.setattr(feishu.request, "urlopen", raise_url_error)

    with pytest.raises(FeishuClientError) as exc:
        FeishuClient()._request_json(feishu.request.Request("https://open.feishu.cn"))

    assert "timed out" in str(exc.value)


def test_send_chat_text_message_posts_to_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FeishuClient()
    monkeypatch.setattr(client, "get_tenant_access_token", lambda: "tenant-token")
    captured = {}

    def fake_post(url, payload, bearer_token=None):
        captured["url"] = url
        captured["payload"] = payload
        captured["bearer_token"] = bearer_token
        return {"code": 0}

    monkeypatch.setattr(client, "_post_json", fake_post)

    client.send_chat_text_message("oc_test", "Import done", uuid="summary-1")

    assert "receive_id_type=chat_id" in captured["url"]
    assert "uuid=summary-1" in captured["url"]
    assert captured["bearer_token"] == "tenant-token"
    assert captured["payload"]["receive_id"] == "oc_test"
    assert captured["payload"]["msg_type"] == "text"
    assert captured["payload"]["content"] == '{"text": "Import done"}'


def test_get_profile_preserves_missing_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FeishuClient()
    monkeypatch.setattr(
        client,
        "_get_json",
        lambda url, token: {"code": 0, "data": {"open_id": "ou_test", "union_id": "on_test"}},
    )

    profile = client.get_profile("user-token")

    assert profile.open_id == "ou_test"
    assert profile.name is None


def test_list_chat_text_messages_parses_official_sender_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FeishuClient()
    monkeypatch.setattr(client, "get_tenant_access_token", lambda: "tenant-token")

    def fake_request(req):
        query = parse_qs(urlparse(req.full_url).query)
        assert query["container_id"] == ["oc_test"]
        assert query["page_size"] == ["20"]
        assert query["sort_type"] == ["ByCreateTimeDesc"]
        assert query["start_time"] == ["1710000000"]
        assert query["end_time"] == ["1717776000"]
        assert query["page_token"] == ["previous-page"]
        return {
            "code": 0,
            "data": {
                "page_token": "next-page",
                "items": [
                    {
                        "message_id": "om_1",
                        "chat_id": "oc_test",
                        "msg_type": "text",
                        "create_time": "1710000000000",
                        "sender": {
                            "id": "ou_alice",
                            "id_type": "open_id",
                            "sender_type": "user",
                            "tenant_key": "tenant_key",
                        },
                        "body": {"content": '{"text":"Need department export for vote results."}'},
                    },
                    {
                        "message_id": "om_2",
                        "msg_type": "image",
                        "sender": {"id": "ou_alice", "id_type": "open_id", "sender_type": "user"},
                        "body": {"content": "{}"},
                    },
                ],
            },
        }

    monkeypatch.setattr(client, "_request_json", fake_request)

    messages, next_token = client.list_chat_text_messages(
        "oc_test",
        page_size=20,
        page_token="previous-page",
        start_time=datetime(2024, 3, 9, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 6, 7, 16, 0, tzinfo=timezone.utc),
    )

    assert next_token == "next-page"
    assert len(messages) == 1
    assert messages[0].message_id == "om_1"
    assert messages[0].sender_open_id == "ou_alice"
    assert messages[0].sender_name is None
    assert messages[0].sender_type == "user"
    assert messages[0].text == "Need department export for vote results."


class _Body:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass
