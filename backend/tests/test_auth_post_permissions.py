from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import router as auth_router
from app.api.routes.posts import router as posts_router, tags_router
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
    app.include_router(posts_router, prefix=settings.api_prefix)
    app.include_router(tags_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)

    def override_db() -> Generator[Session, None, None]:
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    previous_origins = list(settings.cors_origins)
    settings.cors_origins = ["http://localhost:5173"]
    try:
        yield TestClient(app)
    finally:
        settings.cors_origins = previous_origins


def test_anonymous_can_read_but_cannot_write(client: TestClient) -> None:
    response = client.get("/api/v1/posts")
    assert response.status_code == 200
    assert all("comments_count" not in item for item in response.json()["items"])

    response = client.post(
        "/api/v1/posts",
        json={"title": "Need search", "description": "Search would help", "tags": []},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401


def test_origin_validation_fails_closed(client: TestClient) -> None:
    cookies = _cookies("normal-user")
    payload = {"title": "Need export", "description": "Export would help", "tags": []}

    response = client.post("/api/v1/posts", json=payload, cookies=cookies)
    assert response.status_code == 403

    response = client.post(
        "/api/v1/posts",
        json=payload,
        cookies=cookies,
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403


def test_user_can_write_but_not_admin_actions(client: TestClient) -> None:
    cookies = _cookies("normal-user")
    headers = {"Origin": "http://localhost:5173"}

    created = client.post(
        "/api/v1/posts",
        json={"title": "Need export", "description": "Export should work", "tags": []},
        cookies=cookies,
        headers=headers,
    )
    assert created.status_code == 200
    post_id = created.json()["id"]
    assert created.json()["user"]["id"] == "normal-user"

    voted = client.post(f"/api/v1/posts/{post_id}/vote", json={}, cookies=cookies, headers=headers)
    assert voted.status_code == 200

    denied = client.post(
        f"/api/v1/posts/{post_id}/response",
        json={"status": "planned", "text": "Planning"},
        cookies=cookies,
        headers=headers,
    )
    assert denied.status_code == 403

    convert_denied = client.post(
        f"/api/v1/posts/{post_id}/convert-to-task",
        json={"title": "Need export", "description_markdown": "Work item", "labels": ["需求转入"]},
        cookies=cookies,
        headers=headers,
    )
    assert convert_denied.status_code == 403


def test_comment_routes_are_not_available(client: TestClient) -> None:
    assert client.get("/api/v1/posts/missing/comments").status_code == 404
    assert client.post("/api/v1/posts/missing/comments", json={"body": "No longer supported"}).status_code == 404


def test_admin_can_convert_post_to_task(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173"}
    created = client.post(
        "/api/v1/posts",
        json={"title": "Need export", "description": "Export would help", "tags": []},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    assert created.status_code == 200
    post_id = created.json()["id"]

    converted = client.post(
        f"/api/v1/posts/{post_id}/convert-to-task",
        json={"title": "Build export", "description_markdown": "From requirement", "labels": ["需求转入"]},
        cookies=_cookies("admin-user"),
        headers=headers,
    )

    assert converted.status_code == 200
    assert converted.json()["task"]["number"] == 1
    assert converted.json()["post"]["status"] == "in_progress"
    assert converted.json()["post"]["linked_task"]["id"] == converted.json()["task"]["id"]


def test_admin_can_archive_and_normal_reads_hide_archived_post(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173"}
    created = client.post(
        "/api/v1/posts",
        json={"title": "Archive me", "description": "This should be archived", "tags": []},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    assert created.status_code == 200
    post_id = created.json()["id"]

    archived = client.post(f"/api/v1/posts/{post_id}/archive", json={}, cookies=_cookies("admin-user"), headers=headers)
    assert archived.status_code == 200
    assert archived.json()["id"] == post_id

    detail = client.get(f"/api/v1/posts/{post_id}")
    assert detail.status_code == 404

    listed = client.get("/api/v1/posts")
    assert all(item["id"] != post_id for item in listed.json()["items"])


def _cookies(user_id: str) -> dict[str, str]:
    return {settings.auth_cookie_name: create_session_token(user_id)}
