from fastapi import APIRouter, Depends

from app.api.deps import require_current_user, require_mutating_origin
from app.clients.ollama import OllamaSuggestionClient
from app.models.post import UserModel
from app.schemas.ai import SuggestionDraftRequest, SuggestionDraftResponse


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
    return await OllamaSuggestionClient().draft_suggestion(payload.idea)
