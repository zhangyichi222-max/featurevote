from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.posts import PostsRepository
from app.services.posts import PostsService


def get_posts_service(
    session: Session = Depends(get_db_session),
) -> PostsService:
    repository = PostsRepository(session)
    repository.ensure_seed_data()
    return PostsService(repository)
