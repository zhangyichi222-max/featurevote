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
            )
        )
        session.add(
            UserModel(
                id="actor-user",
                tenant_id=DEFAULT_TENANT_ID,
                external_id="actor-open-id",
                feishu_open_id="actor-open-id",
                name="Actor User",
            )
        )
        session.add(
            UserModel(
                id="other-user",
                tenant_id=DEFAULT_TENANT_ID,
                external_id="other-open-id",
                feishu_open_id="other-open-id",
                name="Other User",
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
    assert all("role" not in item["user"] for item in response.json()["items"])

    response = client.post(
        "/api/v1/posts",
        json={"title": "Need search", "description": "Search would help", "tags": []},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401

    current = client.get("/api/v1/auth/me", cookies=_cookies("normal-user"))
    assert current.status_code == 200
    assert current.json()["user"] == {"id": "normal-user", "name": "Normal User"}


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


def test_any_logged_in_user_can_edit_post_content(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173"}
    created = client.post(
        "/api/v1/posts",
        json={"title": "Original title", "description": "Original description", "tags": []},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    assert created.status_code == 200
    original = created.json()

    voted = client.post(
        f"/api/v1/posts/{original['id']}/vote",
        json={},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    assert voted.status_code == 200

    updated = client.patch(
        f"/api/v1/posts/{original['id']}",
        json={"title": "Updated title", "description": "Updated description", "tags": ["Feature"]},
        cookies=_cookies("other-user"),
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Updated title"
    assert body["description"] == "Updated description"
    assert [tag["name"] for tag in body["tags"]] == ["Feature"]
    assert body["slug"] == original["slug"]
    assert body["status"] == original["status"]
    assert body["user"]["id"] == "normal-user"
    assert body["votes_count"] == 1
    assert body["updated_at"] != original["updated_at"]

    partial = client.patch(
        f"/api/v1/posts/{original['id']}",
        json={"description": "Description only update"},
        cookies=_cookies("other-user"),
        headers=headers,
    )
    assert partial.status_code == 200
    assert partial.json()["title"] == "Updated title"
    assert partial.json()["description"] == "Description only update"
    assert [tag["name"] for tag in partial.json()["tags"]] == ["Feature"]


def test_post_edit_requires_login_origin_and_valid_fields(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173"}
    created = client.post(
        "/api/v1/posts",
        json={"title": "Editable post", "description": "Original", "tags": []},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    post_id = created.json()["id"]

    assert client.patch(f"/api/v1/posts/{post_id}", json={"title": "Anonymous edit"}, headers=headers).status_code == 401
    assert client.patch(
        f"/api/v1/posts/{post_id}",
        json={"title": "Missing origin"},
        cookies=_cookies("normal-user"),
    ).status_code == 403
    assert client.patch(
        f"/api/v1/posts/{post_id}",
        json={"description": ""},
        cookies=_cookies("normal-user"),
        headers=headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/posts/{post_id}",
        json={"title": "   "},
        cookies=_cookies("normal-user"),
        headers=headers,
    ).status_code == 422
    unknown_tag = client.patch(
        f"/api/v1/posts/{post_id}",
        json={"tags": ["Unknown label"]},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    assert unknown_tag.status_code == 400


def test_archived_and_missing_posts_cannot_be_edited(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173"}
    created = client.post(
        "/api/v1/posts",
        json={"title": "Archive before edit", "description": "Original", "tags": []},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    post_id = created.json()["id"]
    archived = client.post(
        f"/api/v1/posts/{post_id}/archive",
        json={},
        cookies=_cookies("actor-user"),
        headers=headers,
    )
    assert archived.status_code == 200

    assert client.patch(
        f"/api/v1/posts/{post_id}",
        json={"title": "Too late"},
        cookies=_cookies("other-user"),
        headers=headers,
    ).status_code == 404
    assert client.patch(
        "/api/v1/posts/missing",
        json={"title": "Missing post"},
        cookies=_cookies("other-user"),
        headers=headers,
    ).status_code == 404


def test_logged_in_user_can_manage_posts(client: TestClient) -> None:
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

    status_updated = client.post(
        f"/api/v1/posts/{post_id}/response",
        json={"status": "planned", "text": "Planning"},
        cookies=cookies,
        headers=headers,
    )
    assert status_updated.status_code == 200

    converted = client.post(
        f"/api/v1/posts/{post_id}/convert-to-task",
        json={"title": "Need export", "description_markdown": "Work item", "labels": ["需求转入"]},
        cookies=cookies,
        headers=headers,
    )
    assert converted.status_code == 200


def test_comment_routes_are_not_available(client: TestClient) -> None:
    assert client.get("/api/v1/posts/missing/comments").status_code == 404
    assert client.post("/api/v1/posts/missing/comments", json={"body": "No longer supported"}).status_code == 404


def test_logged_in_user_can_convert_post_to_task(client: TestClient) -> None:
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
        cookies=_cookies("actor-user"),
        headers=headers,
    )

    assert converted.status_code == 200
    assert converted.json()["task"]["number"] == 1
    assert converted.json()["post"]["status"] == "in_progress"
    assert converted.json()["post"]["linked_task"]["id"] == converted.json()["task"]["id"]

    edited = client.patch(
        f"/api/v1/posts/{post_id}",
        json={"title": "Updated after conversion"},
        cookies=_cookies("other-user"),
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "in_progress"
    assert edited.json()["linked_task"]["id"] == converted.json()["task"]["id"]


def test_logged_in_user_can_archive_and_normal_reads_hide_archived_post(client: TestClient) -> None:
    headers = {"Origin": "http://localhost:5173"}
    created = client.post(
        "/api/v1/posts",
        json={"title": "Archive me", "description": "This should be archived", "tags": []},
        cookies=_cookies("normal-user"),
        headers=headers,
    )
    assert created.status_code == 200
    post_id = created.json()["id"]

    archived = client.post(f"/api/v1/posts/{post_id}/archive", json={}, cookies=_cookies("other-user"), headers=headers)
    assert archived.status_code == 200
    assert archived.json()["id"] == post_id

    detail = client.get(f"/api/v1/posts/{post_id}")
    assert detail.status_code == 404

    listed = client.get("/api/v1/posts")
    assert all(item["id"] != post_id for item in listed.json()["items"])


def _cookies(user_id: str) -> dict[str, str]:
    return {settings.auth_cookie_name: create_session_token(user_id)}
