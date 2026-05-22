import io
import json
import zipfile
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.tasks import router as tasks_router
from app.core.config import settings
from app.core.security import create_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.models.post import UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, seed_default_data


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        seed_default_data(session)
        session.add(
            UserModel(
                id="normal-user",
                tenant_id=DEFAULT_TENANT_ID,
                external_id="normal-open-id",
                feishu_open_id="normal-open-id",
                name="Normal User",
                role="visitor",
            )
        )
        session.add(
            UserModel(
                id="admin-user",
                tenant_id=DEFAULT_TENANT_ID,
                external_id="admin-open-id",
                feishu_open_id="admin-open-id",
                name="Admin User",
                role="admin",
            )
        )
        session.commit()

    app = FastAPI()
    app.include_router(tasks_router, prefix=settings.api_prefix)

    def override_db() -> Generator[Session, None, None]:
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    previous_origins = list(settings.cors_origins)
    previous_deepseek_enabled = settings.deepseek_enabled
    settings.cors_origins = ["http://localhost:5173"]
    settings.deepseek_enabled = False
    try:
        yield TestClient(app)
    finally:
        settings.cors_origins = previous_origins
        settings.deepseek_enabled = previous_deepseek_enabled


def test_admin_can_preview_jsonl_import(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/imports/feishu-preview",
        content=_jsonl_bytes(),
        cookies=_cookies("admin-user"),
        headers={**_headers("conversation-logs.jsonl"), "Content-Type": "application/jsonl"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["conversations_count"] == 1
    assert data["messages_count"] == 2
    assert data["candidates"][0]["title"]
    assert data["candidates"][0]["evidence"][0]["conversation_title"] == "产品反馈群"


def test_admin_can_preview_zip_import(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/imports/feishu-preview",
        content=_zip_bytes(),
        cookies=_cookies("admin-user"),
        headers={**_headers("feishu-export.zip"), "Content-Type": "application/zip"},
    )

    assert response.status_code == 200
    assert response.json()["candidates"][0]["evidence"][0]["sender_name"] == "Alice"


def test_import_preview_rejects_malformed_jsonl(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/imports/feishu-preview",
        content=b"{bad",
        cookies=_cookies("admin-user"),
        headers={**_headers("conversation-logs.jsonl"), "Content-Type": "application/jsonl"},
    )

    assert response.status_code == 400
    assert "Invalid JSONL" in response.json()["detail"]


def test_admin_can_create_selected_import_candidates(client: TestClient) -> None:
    preview = client.post(
        "/api/v1/tasks/imports/feishu-preview",
        content=_jsonl_bytes(),
        cookies=_cookies("admin-user"),
        headers={**_headers("conversation-logs.jsonl"), "Content-Type": "application/jsonl"},
    )
    candidate = preview.json()["candidates"][0]

    created = client.post(
        "/api/v1/tasks/imports/feishu-create",
        json={"candidates": [candidate]},
        cookies=_cookies("admin-user"),
        headers={"Origin": "http://localhost:5173"},
    )

    assert created.status_code == 200
    task = created.json()["items"][0]
    assert task["number"] == 1
    assert task["status"] == "todo"
    assert task["assignee"] is None
    assert "来源消息证据" in task["description_markdown"]


def test_non_admin_cannot_import_feishu_tasks(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/imports/feishu-preview",
        content=_jsonl_bytes(),
        cookies=_cookies("normal-user"),
        headers={**_headers("conversation-logs.jsonl"), "Content-Type": "application/jsonl"},
    )

    assert response.status_code == 403


def _jsonl_bytes() -> bytes:
    record = {
        "id": "conversation-1",
        "createdAt": "2026-05-22T00:00:00Z",
        "sourceType": "chat",
        "sourceId": "chat-1",
        "sourceTitle": "产品反馈群",
        "messages": [
            {
                "content": "帮忙修复导出失败问题，用户无法下载报表",
                "create_time": "2026-05-22 10:00",
                "deleted": False,
                "message_id": "message-1",
                "msg_type": "text",
                "sender": {"id": "ou_alice", "name": "Alice", "sender_type": "user"},
            },
            {
                "content": "好的",
                "create_time": "2026-05-22 10:01",
                "deleted": False,
                "message_id": "message-2",
                "msg_type": "text",
                "sender": {"id": "ou_bob", "name": "Bob", "sender_type": "user"},
            },
        ],
    }
    return (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")


def _zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("data/conversation-logs.jsonl", _jsonl_bytes())
    return output.getvalue()


def _headers(filename: str) -> dict[str, str]:
    return {"Origin": "http://localhost:5173", "X-File-Name": filename}


def _cookies(user_id: str) -> dict[str, str]:
    return {settings.auth_cookie_name: create_session_token(user_id)}
