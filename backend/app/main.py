from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app import models  # noqa: F401
from app.api.routes.posts import router as posts_router, tags_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.repositories.posts import seed_default_data


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(posts_router, prefix=settings.api_prefix)
app.include_router(tags_router, prefix=settings.api_prefix)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_default_data(session)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=settings.app_env == "dev")
