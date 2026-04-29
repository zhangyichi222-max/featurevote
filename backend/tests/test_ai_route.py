from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.ai import router as ai_router
from app.clients.ollama import OllamaSuggestionClient
from app.core.config import settings
from app.core.security import create_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.models.post import UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, seed_default_data
from app.schemas.ai import SuggestionDraftResponse


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
        session.commit()

    app = FastAPI()
    app.include_router(ai_router, prefix=settings.api_prefix)

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


def test_ai_draft_requires_login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/suggestion-draft",
        json={"idea": "Need a clearer way to export voting results by department"},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 401


def test_ai_draft_requires_allowed_origin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/suggestion-draft",
        json={"idea": "Need a clearer way to export voting results by department"},
        cookies=_cookies("normal-user"),
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 403


def test_ai_draft_returns_generated_suggestion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def draft_suggestion(self, idea: str) -> SuggestionDraftResponse:
        _ = self, idea
        return SuggestionDraftResponse(
            title="支持导出投票结果",
            description="问题：当前无法导出。\n\n场景：复盘会议。\n\n期望结果：可以下载表格。",
        )

    monkeypatch.setattr(OllamaSuggestionClient, "draft_suggestion", draft_suggestion)

    response = client.post(
        "/api/v1/ai/suggestion-draft",
        json={"idea": "Need a clearer way to export voting results by department"},
        cookies=_cookies("normal-user"),
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "支持导出投票结果"


def _cookies(user_id: str) -> dict[str, str]:
    return {settings.auth_cookie_name: create_session_token(user_id)}
