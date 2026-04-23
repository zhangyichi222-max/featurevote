from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.requirements import RequirementsRepository
from app.services.requirements import RequirementsService


def get_requirements_service(
    session: Session = Depends(get_db_session),
) -> RequirementsService:
    repository = RequirementsRepository(session)
    return RequirementsService(repository)
