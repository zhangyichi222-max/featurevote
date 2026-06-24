from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_current_user, require_mutating_origin
from app.db.session import get_db_session
from app.models.post import UserModel
from app.repositories.posts import PostsRepository
from app.schemas.feishu_import import FeishuImportRunResponse
from app.services.feishu_import import FeishuRequirementImportService


router = APIRouter(prefix="/feishu-import", tags=["feishu-import"])


@router.post("/run", response_model=FeishuImportRunResponse, dependencies=[Depends(require_mutating_origin)])
async def run_feishu_import(
    user: UserModel = Depends(require_current_user),
    session: Session = Depends(get_db_session),
) -> FeishuImportRunResponse:
    _ = user
    repository = PostsRepository(session)
    repository.ensure_seed_data()
    return await FeishuRequirementImportService(repository).import_configured_chats()
