from __future__ import annotations

import hashlib
import logging

from app.clients.ollama import OllamaEmbeddingClient
from app.clients.qdrant import QdrantClient
from app.core.config import settings
from app.models.post import PostModel, utc_now
from app.repositories.posts import PostsRepository


logger = logging.getLogger(__name__)


def embedding_text(title: str, description: str) -> str:
    return f"{title.strip()}\n\n{description.strip()}".strip()


def content_hash(title: str, description: str) -> str:
    return hashlib.sha256(embedding_text(title, description).encode("utf-8")).hexdigest()


class PostEmbeddingIndexService:
    def __init__(
        self,
        repository: PostsRepository,
        embedding_client: OllamaEmbeddingClient | None = None,
        vector_client: QdrantClient | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client or OllamaEmbeddingClient()
        self.vector_client = vector_client or QdrantClient()

    async def index_post(self, post: PostModel) -> bool:
        digest = content_hash(post.title, post.description)
        try:
            await self.vector_client.ensure_collection()
            vector = await self.embedding_client.embed(embedding_text(post.title, post.description))
            await self.vector_client.upsert(
                post.id,
                vector,
                {
                    "tenant_id": post.tenant_id,
                    "number": post.number,
                    "model": settings.ollama_embedding_model,
                },
            )
        except Exception as exc:  # noqa: BLE001 - indexing must not block business writes.
            logger.warning("Requirement embedding index failed for %s: %s", post.id, exc)
            self.repository.save_embedding_index_state(
                post.id,
                model=settings.ollama_embedding_model,
                content_hash=digest,
                status="failed",
                error=str(exc),
            )
            return False

        self.repository.save_embedding_index_state(
            post.id,
            model=settings.ollama_embedding_model,
            content_hash=digest,
            status="indexed",
            indexed_at=utc_now(),
        )
        return True

    async def remove_post(self, post_id: str) -> bool:
        try:
            await self.vector_client.delete(post_id)
            self.repository.mark_embedding_index_removed(post_id)
            return True
        except Exception as exc:  # noqa: BLE001 - index cleanup is recoverable.
            logger.warning("Requirement embedding removal failed for %s: %s", post_id, exc)
            self.repository.mark_embedding_index_removed(post_id, error=str(exc))
            return False

    async def rebuild(self) -> tuple[int, int]:
        indexed = 0
        failed = 0
        for post in self.repository.list_active_post_models():
            if await self.index_post(post):
                indexed += 1
            else:
                failed += 1
        return indexed, failed
