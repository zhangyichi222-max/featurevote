from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, parse, request

from app.core.config import settings


class FeishuClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeishuProfile:
    open_id: str
    union_id: str | None
    name: str
    email: str | None
    avatar_url: str | None
    department_ids: list[str]
    group_ids: list[str]


@dataclass(frozen=True)
class FeishuChatMessage:
    message_id: str
    chat_id: str
    sender_open_id: str
    sender_name: str | None
    sender_type: str | None
    text: str
    sent_at: datetime | None


class FeishuClient:
    authorization_url = "https://open.feishu.cn/open-apis/authen/v1/index"
    tenant_token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    token_url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    user_info_url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
    message_url = "https://open.feishu.cn/open-apis/im/v1/messages"

    def build_authorization_url(self, state: str) -> str:
        if not settings.feishu_app_id or not settings.feishu_redirect_uri:
            raise FeishuClientError("Feishu OAuth is not configured.")
        query = parse.urlencode(
            {
                "app_id": settings.feishu_app_id,
                "redirect_uri": settings.feishu_redirect_uri,
                "state": state,
            }
        )
        return f"{self.authorization_url}?{query}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.feishu_app_id,
            "client_secret": settings.feishu_app_secret,
            "redirect_uri": settings.feishu_redirect_uri,
        }
        data = self._post_json(self.token_url, payload)
        if "access_token" in data:
            return data
        nested = data.get("data")
        if isinstance(nested, dict) and "access_token" in nested:
            return nested
        raise FeishuClientError("Feishu token response did not include an access token.")

    def get_profile(self, access_token: str) -> FeishuProfile:
        data = self._get_json(self.user_info_url, access_token)
        source = data.get("data") if isinstance(data.get("data"), dict) else data
        open_id = _first_str(source, "open_id", "sub", "user_id")
        if not open_id:
            raise FeishuClientError("Feishu profile response did not include open_id.")
        return FeishuProfile(
            open_id=open_id,
            union_id=_first_str(source, "union_id"),
            name=_first_str(source, "name", "display_name", "en_name") or "Feishu User",
            email=_first_str(source, "email"),
            avatar_url=_first_str(source, "avatar_url", "avatar_thumb"),
            department_ids=_string_list(source.get("department_ids") or source.get("department_id")),
            group_ids=_string_list(source.get("group_ids") or source.get("groups")),
        )

    def authenticate_code(self, code: str) -> FeishuProfile:
        token = self.exchange_code(code)
        return self.get_profile(str(token["access_token"]))

    def get_tenant_access_token(self) -> str:
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise FeishuClientError("Feishu app credentials are not configured.")
        data = self._post_json(
            self.tenant_token_url,
            {
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
        token = data.get("tenant_access_token")
        if isinstance(token, str) and token:
            return token
        raise FeishuClientError("Feishu tenant token response did not include tenant_access_token.")

    def send_text_message(self, open_id: str, text: str, uuid: str | None = None) -> None:
        token = self.get_tenant_access_token()
        params = {"receive_id_type": "open_id"}
        if uuid:
            params["uuid"] = uuid
        url = f"{self.message_url}?{parse.urlencode(params)}"
        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        self._post_json(url, payload, bearer_token=token)

    def send_chat_text_message(self, chat_id: str, text: str, uuid: str | None = None) -> None:
        token = self.get_tenant_access_token()
        params = {"receive_id_type": "chat_id"}
        if uuid:
            params["uuid"] = uuid
        url = f"{self.message_url}?{parse.urlencode(params)}"
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        self._post_json(url, payload, bearer_token=token)

    def list_chat_text_messages(
        self,
        chat_id: str,
        *,
        page_size: int = 50,
        page_token: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[FeishuChatMessage], str | None]:
        token = self.get_tenant_access_token()
        params: dict[str, str | int] = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "page_size": max(1, min(page_size, 50)),
            "sort_type": "ByCreateTimeDesc",
        }
        if page_token:
            params["page_token"] = page_token
        if start_time:
            params["start_time"] = int(start_time.timestamp())
        if end_time:
            params["end_time"] = int(end_time.timestamp())
        url = f"{self.message_url}?{parse.urlencode(params)}"
        data = self._get_json(url, token)
        source = data.get("data") if isinstance(data.get("data"), dict) else {}
        raw_items = source.get("items") if isinstance(source, dict) else []
        if not isinstance(raw_items, list):
            raw_items = []
        messages = [
            message
            for item in raw_items
            if isinstance(item, dict)
            for message in [_parse_chat_message(item, chat_id)]
            if message is not None
        ]
        next_token = source.get("page_token") if isinstance(source, dict) else None
        return messages, next_token if isinstance(next_token, str) and next_token else None

    def _post_json(self, url: str, payload: dict[str, Any], bearer_token: str | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        req = request.Request(url, data=body, headers=headers, method="POST")
        return self._request_json(req)

    def _get_json(self, url: str, bearer_token: str) -> dict[str, Any]:
        req = request.Request(url, headers={"Authorization": f"Bearer {bearer_token}"}, method="GET")
        return self._request_json(req)

    def _request_json(self, req: request.Request) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = _read_error_body(exc)
            raise FeishuClientError(
                f"Feishu API request failed with HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise FeishuClientError(f"Feishu API request failed: {exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001 - convert provider failures into a stable app error.
            raise FeishuClientError(f"Feishu API request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise FeishuClientError("Feishu API response was not an object.")
        code = payload.get("code")
        if code not in (None, 0):
            raise FeishuClientError(str(payload.get("msg") or "Feishu API returned an error."))
        return payload


def _first_str(source: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 - best effort diagnostic detail.
        return ""
    return body[:500]


def _parse_chat_message(item: dict[str, Any], chat_id: str) -> FeishuChatMessage | None:
    if item.get("msg_type") != "text":
        return None

    message_id = _first_str(item, "message_id")
    if not message_id:
        return None

    sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
    sender_open_id = _first_str(sender, "id")
    if not sender_open_id:
        return None

    text = _extract_text_content(item.get("body"))
    if not text:
        return None

    return FeishuChatMessage(
        message_id=message_id,
        chat_id=_first_str(item, "chat_id") or chat_id,
        sender_open_id=sender_open_id,
        sender_name=_first_str(sender, "sender_name"),
        sender_type=_first_str(sender, "sender_type"),
        text=text,
        sent_at=_parse_millis_datetime(_first_str(item, "create_time", "update_time")),
    )


def _extract_text_content(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    content = body.get("content")
    if not isinstance(content, str):
        return ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content.strip()
    if not isinstance(parsed, dict):
        return ""
    text = parsed.get("text")
    return text.strip() if isinstance(text, str) else ""


def _parse_millis_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = int(value)
    except ValueError:
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
