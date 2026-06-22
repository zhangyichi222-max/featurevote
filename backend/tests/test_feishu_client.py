from urllib import error

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


def test_list_chat_text_messages_parses_text_and_next_page(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FeishuClient()
    monkeypatch.setattr(client, "get_tenant_access_token", lambda: "tenant-token")

    def fake_request(req):
        assert "container_id=oc_test" in req.full_url
        assert "page_size=20" in req.full_url
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
                            "sender_name": "Alice",
                            "sender_id": {"open_id": "ou_alice", "sender_type": "user"},
                        },
                        "body": {"content": '{"text":"希望支持按部门导出投票结果"}'},
                    },
                    {
                        "message_id": "om_2",
                        "msg_type": "image",
                        "sender": {"sender_id": {"open_id": "ou_alice"}},
                        "body": {"content": "{}"},
                    },
                ],
            },
        }

    monkeypatch.setattr(client, "_request_json", fake_request)

    messages, next_token = client.list_chat_text_messages("oc_test", page_size=20)

    assert next_token == "next-page"
    assert len(messages) == 1
    assert messages[0].message_id == "om_1"
    assert messages[0].sender_open_id == "ou_alice"
    assert messages[0].sender_name == "Alice"
    assert messages[0].text == "希望支持按部门导出投票结果"


class _Body:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass
