import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_mysql_env_from_bashrc() -> None:
    bashrc_path = Path.home() / ".bashrc"
    if not bashrc_path.is_file():
        return

    for raw_line in bashrc_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("export MYSQL_") or "=" not in line:
            continue

        key, value = line[len("export ") :].split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


_load_mysql_env_from_bashrc()


class Settings(BaseSettings):
    app_name: str = "FeatureVote API"
    app_env: str = "dev"
    app_port: int = 8090
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]
    cors_origin_regex: str | None = r"^https?://[^/]+:5173$"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "featurevote"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

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
