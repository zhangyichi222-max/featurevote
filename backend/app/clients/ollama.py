from __future__ import annotations

import httpx

from app.core.config import settings


class EmbeddingServiceError(RuntimeError):
    pass


class OllamaEmbeddingClient:
    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
                response = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/embed",
                    json={"model": settings.ollama_embedding_model, "input": text},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingServiceError(f"Ollama embedding request failed: {exc}") from exc

        payload = response.json()
        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
            raise EmbeddingServiceError("Ollama returned an invalid embedding response.")
        vector = [float(value) for value in embeddings[0]]
        if len(vector) != settings.ollama_embedding_dimensions:
            raise EmbeddingServiceError(
                f"Embedding dimension mismatch: expected {settings.ollama_embedding_dimensions}, got {len(vector)}."
            )
        return vector
