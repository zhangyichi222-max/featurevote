from __future__ import annotations

import asyncio
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.repositories.posts import PostsRepository  # noqa: E402
from app.services.embedding_index import PostEmbeddingIndexService  # noqa: E402


async def main() -> int:
    with SessionLocal() as session:
        indexed, failed = await PostEmbeddingIndexService(PostsRepository(session)).rebuild()
    print(f"Requirement embedding rebuild completed: indexed={indexed}, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
