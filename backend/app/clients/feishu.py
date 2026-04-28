from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import parse, request

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


class FeishuClient:
    authorization_url = "https://open.feishu.cn/open-apis/authen/v1/index"
    token_url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    user_info_url = "https://open.feishu.cn/open-apis/authen/v1/user_info"

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

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        return self._request_json(req)

    def _get_json(self, url: str, bearer_token: str) -> dict[str, Any]:
        req = request.Request(url, headers={"Authorization": f"Bearer {bearer_token}"}, method="GET")
        return self._request_json(req)

    def _request_json(self, req: request.Request) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - convert provider failures into a stable app error.
            raise FeishuClientError("Feishu API request failed.") from exc
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
