from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_current_user, require_mutating_origin
from app.clients.deepseek import DeepSeekSuggestionClient
from app.db.session import get_db_session
from app.models.post import UserModel
from app.repositories.posts import PostsRepository
from app.schemas.ai import (
    SimilarRequirementsRequest,
    SimilarRequirementsResponse,
    SuggestionDraftRequest,
    SuggestionDraftResponse,
)
from app.services.similarity import SimilarRequirementsService


router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/suggestion-draft",
    response_model=SuggestionDraftResponse,
    dependencies=[Depends(require_mutating_origin)],
)
async def draft_suggestion(
    payload: SuggestionDraftRequest,
    user: UserModel = Depends(require_current_user),
) -> SuggestionDraftResponse:
    _ = user
    return await DeepSeekSuggestionClient().draft_suggestion(payload.idea)


@router.post(
    "/similar-requirements",
    response_model=SimilarRequirementsResponse,
    dependencies=[Depends(require_mutating_origin)],
)
async def similar_requirements(
    payload: SimilarRequirementsRequest,
    user: UserModel = Depends(require_current_user),
    session: Session = Depends(get_db_session),
) -> SimilarRequirementsResponse:
    _ = user
    return await SimilarRequirementsService(PostsRepository(session)).find_similar(payload)
