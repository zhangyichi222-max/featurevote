import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, require_mutating_origin
from app.core.config import settings
from app.core.security import create_session_token, create_state_token
from app.db.session import get_db_session
from app.models.post import UserModel
from app.repositories.posts import PostsRepository
from app.schemas.auth import AuthActionResult, AuthMeResponse, ClientCodeExchange
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "featurevote_feishu_oauth_state"
logger = logging.getLogger(__name__)


@router.get("/feishu/browser/start")
async def start_browser_login(session: Session = Depends(get_db_session)) -> RedirectResponse:
    PostsRepository(session).ensure_seed_data()
    state = create_state_token()
    try:
        logger.info("Starting Feishu browser login with redirect_uri=%s", settings.feishu_redirect_uri)
        url = AuthService(session).build_browser_authorization_url(state)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    response = RedirectResponse(url)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=600,
        path="/",
    )
    return response


@router.get("/feishu/browser/callback")
async def browser_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or expected_state != state:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Feishu OAuth state.")
    try:
        user = AuthService(session).authenticate_feishu_code(code)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    response = RedirectResponse(f"{settings.frontend_base_url}?auth=success")
    _set_auth_cookie(response, user)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


@router.post(
    "/feishu/client/exchange",
    response_model=AuthMeResponse,
    dependencies=[Depends(require_mutating_origin)],
)
async def client_exchange(
    payload: ClientCodeExchange,
    response: Response,
    session: Session = Depends(get_db_session),
) -> AuthMeResponse:
    try:
        user = AuthService(session).authenticate_feishu_code(payload.code)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    _set_auth_cookie(response, user)
    return AuthMeResponse(user=_to_user_item(user))


@router.get("/me", response_model=AuthMeResponse)
async def me(user: UserModel | None = Depends(get_current_user_optional)) -> AuthMeResponse:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return AuthMeResponse(user=_to_user_item(user))


@router.post("/logout", response_model=AuthActionResult, dependencies=[Depends(require_mutating_origin)])
async def logout(response: Response) -> AuthActionResult:
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return AuthActionResult(message="Logged out.")


def _set_auth_cookie(response: Response, user: UserModel) -> None:
    response.set_cookie(
        settings.auth_cookie_name,
        create_session_token(user.id),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.auth_token_ttl_seconds,
        path="/",
    )


def _to_user_item(user: UserModel):
    return {"id": user.id, "name": user.name}
