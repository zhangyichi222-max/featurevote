from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from secrets import token_urlsafe
from typing import Any

from app.core.config import settings


class TokenError(ValueError):
    pass


def create_state_token() -> str:
    return token_urlsafe(32)


def create_session_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.auth_token_ttl_seconds,
    }
    return _encode(payload)


def verify_session_token(token: str) -> str:
    payload = _decode(token)
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("Session token is missing subject.")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        raise TokenError("Session token has expired.")
    return subject


def _encode(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = _b64_bytes(_sign(signing_input.encode("ascii")))
    return f"{signing_input}.{signature}"


def _decode(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Session token format is invalid.")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = _b64_bytes(_sign(signing_input))
    if not hmac.compare_digest(expected, parts[2]):
        raise TokenError("Session token signature is invalid.")
    try:
        payload = json.loads(_unb64(parts[1]).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("Session token payload is invalid.") from exc
    if not isinstance(payload, dict):
        raise TokenError("Session token payload is invalid.")
    return payload


def _sign(value: bytes) -> bytes:
    return hmac.new(settings.auth_token_secret.encode("utf-8"), value, hashlib.sha256).digest()


def _b64_json(value: dict[str, Any]) -> str:
    return _b64_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
