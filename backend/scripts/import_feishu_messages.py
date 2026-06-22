from pathlib import Path
import argparse
import asyncio
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.posts import PostsRepository
from app.services.feishu_import import FeishuRequirementImportService


async def import_once() -> int:
    with SessionLocal() as session:
        repository = PostsRepository(session)
        repository.ensure_seed_data()
        stats = await FeishuRequirementImportService(repository).import_configured_chats()
    total_actions = stats.created + stats.voted + stats.already_voted + stats.failed + stats.skipped
    print(
        "Feishu import: "
        f"fetched={stats.fetched}, skipped={stats.skipped}, created={stats.created}, "
        f"voted={stats.voted}, already_voted={stats.already_voted}, failed={stats.failed}, "
        f"windows_processed={stats.windows_processed}, generated_requirements={stats.generated_requirements}, "
        f"grouped_messages={stats.grouped_messages}, low_confidence_skipped={stats.low_confidence_skipped}",
        flush=True,
    )
    return total_actions


def process_once() -> int:
    return asyncio.run(import_once())


def watch(interval: float) -> None:
    print(f"Watching Feishu chats every {interval:g} second(s).", flush=True)
    while True:
        process_once()
        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Feishu chat messages into FeatureVote requirements.")
    parser.add_argument("--once", action="store_true", help="Run a single import pass and exit.")
    parser.add_argument("--watch", action="store_true", help="Keep polling configured Feishu chats.")
    parser.add_argument(
        "--interval",
        type=float,
        default=settings.feishu_import_interval_seconds,
        help="Polling interval in seconds when --watch is enabled.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than 0.")
    if args.watch:
        watch(args.interval)
        return
    process_once()


if __name__ == "__main__":
    main()
