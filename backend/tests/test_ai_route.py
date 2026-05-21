from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.ai import router as ai_router
from app.clients.deepseek import DeepSeekSuggestionClient
from app.core.config import settings
from app.core.security import create_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.models.post import PostModel, UserModel
from app.repositories.posts import DEFAULT_TENANT_ID, seed_default_data
from app.schemas.ai import SimilarRequirementItem, SuggestionDraftResponse


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
            PostModel(
                id="export-post",
                tenant_id=DEFAULT_TENANT_ID,
                user_id="normal-user",
                number=1,
                title="Export voting results by department",
                slug="export-voting-results-by-department",
                description="Let admins export vote totals grouped by department as a CSV report.",
                status="open",
                is_approved=True,
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
    previous_deepseek_enabled = settings.deepseek_enabled
    settings.cors_origins = ["http://localhost:5173"]
    settings.deepseek_enabled = False
    try:
        yield TestClient(app)
    finally:
        settings.cors_origins = previous_origins
        settings.deepseek_enabled = previous_deepseek_enabled


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

    monkeypatch.setattr(DeepSeekSuggestionClient, "draft_suggestion", draft_suggestion)

    response = client.post(
        "/api/v1/ai/suggestion-draft",
        json={"idea": "Need a clearer way to export voting results by department"},
        cookies=_cookies("normal-user"),
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "支持导出投票结果"


def test_similar_requirements_uses_text_similarity_without_deepseek(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/similar-requirements",
        json={
            "title": "Department export for vote results",
            "description": "We need a CSV export of voting totals grouped by department.",
        },
        cookies=_cookies("normal-user"),
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ai_enhanced"] is False
    assert data["items"][0]["id"] == "export-post"
    assert data["items"][0]["similarity"] > 0


def test_similar_requirements_can_use_deepseek_enhancement(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def assess_similar_requirements(
        self,
        title: str,
        description: str,
        candidates: list[SimilarRequirementItem],
    ) -> list[SimilarRequirementItem]:
        _ = self, title, description
        return [
            candidates[0].model_copy(
                update={
                    "similarity": 0.91,
                    "is_high_confidence": True,
                    "reason": "Both ask for department-level vote exports.",
                }
            )
        ]

    monkeypatch.setattr(DeepSeekSuggestionClient, "assess_similar_requirements", assess_similar_requirements)

    response = client.post(
        "/api/v1/ai/similar-requirements",
        json={
            "title": "Department export for vote results",
            "description": "We need a CSV export of voting totals grouped by department.",
        },
        cookies=_cookies("normal-user"),
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["similarity"] == 0.91
    assert item["is_high_confidence"] is True
    assert item["reason"] == "Both ask for department-level vote exports."


def _cookies(user_id: str) -> dict[str, str]:
    return {settings.auth_cookie_name: create_session_token(user_id)}
