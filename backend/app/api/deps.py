from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import is_origin_allowed, settings
from app.core.security import TokenError, verify_session_token
from app.db.session import get_db_session
from app.models.post import UserModel
from app.repositories.posts import PostsRepository
from app.repositories.tasks import TasksRepository
from app.services.posts import PostsService
from app.services.tasks import TasksService


def get_posts_service(
    session: Session = Depends(get_db_session),
) -> PostsService:
    repository = PostsRepository(session)
    repository.ensure_seed_data()
    return PostsService(repository)


def get_tasks_service(
    session: Session = Depends(get_db_session),
) -> TasksService:
    return TasksService(TasksRepository(session))


def get_current_user_optional(
    request: Request,
    session: Session = Depends(get_db_session),
) -> UserModel | None:
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    try:
        user_id = verify_session_token(token)
    except TokenError:
        return None
    return session.get(UserModel, user_id)


def require_current_user(
    user: UserModel | None = Depends(get_current_user_optional),
) -> UserModel:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


def require_mutating_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not is_origin_allowed(origin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed.")
