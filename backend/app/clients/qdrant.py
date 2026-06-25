from __future__ import annotations

from uuid import UUID
from time import monotonic

import httpx

from app.core.config import settings


class VectorStoreError(RuntimeError):
    pass


class QdrantClient:
    _unavailable_until = 0.0

    async def ensure_collection(self) -> None:
        if monotonic() < self._unavailable_until:
            raise VectorStoreError("Qdrant is temporarily unavailable.")
        collection_url = self._collection_url()
        try:
            async with httpx.AsyncClient(timeout=settings.qdrant_timeout) as client:
                response = await client.get(collection_url)
                if response.status_code == 404:
                    response = await client.put(
                        collection_url,
                        json={
                            "vectors": {
                                "size": settings.ollama_embedding_dimensions,
                                "distance": "Cosine",
                            }
                        },
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            type(self)._unavailable_until = monotonic() + 30
            raise VectorStoreError(f"Qdrant collection check failed: {exc}") from exc

    async def upsert(self, post_id: str, vector: list[float], payload: dict[str, object]) -> None:
        await self.ensure_collection()
        try:
            async with httpx.AsyncClient(timeout=settings.qdrant_timeout) as client:
                response = await client.put(
                    f"{self._collection_url()}/points?wait=true",
                    json={
                        "points": [
                            {
                                "id": str(UUID(hex=post_id)),
                                "vector": vector,
                                "payload": {**payload, "post_id": post_id},
                            }
                        ]
                    },
                )
                response.raise_for_status()
        except (ValueError, httpx.HTTPError) as exc:
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc

    async def delete(self, post_id: str) -> None:
        await self.ensure_collection()
        try:
            point_id = str(UUID(hex=post_id))
            async with httpx.AsyncClient(timeout=settings.qdrant_timeout) as client:
                response = await client.post(
                    f"{self._collection_url()}/points/delete?wait=true",
                    json={"points": [point_id]},
                )
                response.raise_for_status()
        except (ValueError, httpx.HTTPError) as exc:
            raise VectorStoreError(f"Qdrant delete failed: {exc}") from exc

    async def search(self, vector: list[float], limit: int) -> list[tuple[str, float]]:
        await self.ensure_collection()
        try:
            async with httpx.AsyncClient(timeout=settings.qdrant_timeout) as client:
                response = await client.post(
                    f"{self._collection_url()}/points/search",
                    json={"vector": vector, "limit": limit, "with_payload": True},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc

        body = response.json()
        results = body.get("result") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise VectorStoreError("Qdrant returned an invalid search response.")
        output: list[tuple[str, float]] = []
        for item in results:
            payload = item.get("payload") if isinstance(item, dict) else None
            post_id = payload.get("post_id") if isinstance(payload, dict) else None
            score = item.get("score") if isinstance(item, dict) else None
            if isinstance(post_id, str) and isinstance(score, (int, float)):
                output.append((post_id, float(score)))
        return output

    def _collection_url(self) -> str:
        return f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}"
