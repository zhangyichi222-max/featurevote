from app.core.config import settings
from app.repositories.requirements import RequirementsRepository
from app.services.requirements import RequirementsService


repository = RequirementsRepository(settings.sqlite_db_path)


def get_requirements_service() -> RequirementsService:
    return RequirementsService(repository)
