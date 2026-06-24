import json
import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_SUPPORTED_SERVER_ENV_PREFIXES = (
    "MYSQL_",
    "FEISHU_",
    "FRONTEND_",
    "DEEPSEEK_",
    "MINIO_",
    "TASK_",
    "ATTACHMENT_",
)


def _iter_env_assignments(path: Path, *, require_export: bool) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        elif require_export:
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith(_SUPPORTED_SERVER_ENV_PREFIXES):
            continue
        values[key] = value.strip().strip("\"'")
    return values


def _load_server_env_from_files() -> None:
    dotenv_values = _iter_env_assignments(Path(".env"), require_export=False)
    bashrc_path = Path.home() / ".bashrc"
    bashrc_values = _iter_env_assignments(bashrc_path, require_export=True)

    for key, value in dotenv_values.items():
        os.environ[key] = value

    for key, value in bashrc_values.items():
        if key in dotenv_values:
            continue
        os.environ[key] = value


_load_server_env_from_files()


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
    cors_origins: list[str] = ["http://localhost:5173", "http://192.168.200.33:5173"]
    cors_origin_regex: str | None = None
    frontend_base_url: str = "http://192.168.200.33:5173"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "featurevote"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_redirect_uri: str = "http://192.168.200.33:8090/api/v1/auth/feishu/browser/callback"
    feishu_import_chat_ids: list[str] = []
    feishu_import_interval_seconds: float = 60
    feishu_import_batch_size: int = 50
    feishu_import_default_tags: list[str] = ["飞书导入"]
    feishu_import_duplicate_threshold: float = 0.72
    feishu_import_notify_chat: bool = True
    feishu_import_grouping_enabled: bool = True
    feishu_import_window_minutes: int = 60
    feishu_import_min_confidence: float = 0.65
    feishu_import_max_messages_per_summary: int = 50
    feishu_import_debug_logging: bool = False
    feishu_import_debug_log_max_chars: int = 4000
    auth_cookie_name: str = "featurevote_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_token_secret: str = "dev-featurevote-change-me"
    auth_token_ttl_seconds: int = 7 * 24 * 60 * 60
    deepseek_enabled: bool = True
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_thinking: str = "enabled"
    deepseek_reasoning_effort: str = "high"
    deepseek_timeout: float = 30
    deepseek_max_text_chars: int = 12000
    deepseek_min_text_chars: int = 20
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "featurevote"
    minio_public_base_url: str = ""
    minio_secure: bool = False
    task_image_max_bytes: int = 5 * 1024 * 1024
    attachment_max_bytes: int = 20 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", enable_decoding=False)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        return _parse_str_list(value)

    @field_validator(
        "feishu_import_chat_ids",
        "feishu_import_default_tags",
        mode="before",
    )
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
    _load_server_env_from_files()
    return Settings()


settings = get_settings()


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in settings.cors_origins:
        return True
    return bool(settings.cors_origin_regex and re.fullmatch(settings.cors_origin_regex, origin))
