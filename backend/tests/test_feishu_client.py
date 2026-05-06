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


class _Body:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass
