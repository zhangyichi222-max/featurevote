import json
import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_server_env_from_bashrc() -> None:
    bashrc_path = Path.home() / ".bashrc"
    if not bashrc_path.is_file():
        return

    supported_prefixes = ("MYSQL_", "FEISHU_", "FRONTEND_")
    for raw_line in bashrc_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("export ") or "=" not in line:
            continue

        key, value = line[len("export ") :].split("=", 1)
        key = key.strip()
        if not key.startswith(supported_prefixes):
            continue
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


_load_server_env_from_bashrc()


def _parse_str_list(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    app_name: str = "FeatureVote API"
    app_env: str = "dev"
    app_port: int = 8090
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cors_origin_regex: str | None = None
    frontend_base_url: str = "http://localhost:5173"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "featurevote"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_redirect_uri: str = "http://localhost:8090/api/v1/auth/feishu/browser/callback"
    feishu_admin_department_ids: list[str] = []
    feishu_admin_group_ids: list[str] = []
    auth_cookie_name: str = "featurevote_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_token_secret: str = "dev-featurevote-change-me"
    auth_token_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", enable_decoding=False)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        return _parse_str_list(value)

    @field_validator("feishu_admin_department_ids", "feishu_admin_group_ids", mode="before")
    @classmethod
    def parse_id_list(cls, value: str | list[str]) -> list[str]:
        return _parse_str_list(value)

    @field_validator("cors_origin_regex", mode="before")
    @classmethod
    def parse_cors_origin_regex(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in settings.cors_origins:
        return True
    return bool(settings.cors_origin_regex and re.fullmatch(settings.cors_origin_regex, origin))
