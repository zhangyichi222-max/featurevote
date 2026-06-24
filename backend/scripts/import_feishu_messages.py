from pathlib import Path
import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.posts import PostsRepository
from app.services.feishu_import import FeishuRequirementImportService


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


class BeijingTimeFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        current = datetime.fromtimestamp(record.created, tz=BEIJING_TIMEZONE)
        return current.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def configure_logging() -> None:
    level = logging.INFO if settings.feishu_import_debug_logging else logging.WARNING
    handler = logging.StreamHandler()
    handler.setFormatter(BeijingTimeFormatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def import_once() -> int:
    with SessionLocal() as session:
        repository = PostsRepository(session)
        repository.ensure_seed_data()
        stats = await FeishuRequirementImportService(repository).import_configured_chats()
    total_actions = stats.created + stats.voted + stats.already_voted + stats.failed + stats.skipped
    print(
        "导入完成："
        f"读取 {stats.fetched}，跳过 {stats.skipped}，新增 {stats.created}，"
        f"重复需求加票 {stats.voted}，已投过票 {stats.already_voted}，失败 {stats.failed}",
        flush=True,
    )
    return total_actions


def process_once() -> int:
    return asyncio.run(import_once())


def watch(interval: float) -> None:
    print(f"开始监听飞书群，每 {interval:g} 秒检查一次。", flush=True)
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
    configure_utf8_output()
    configure_logging()
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than 0.")
    if args.watch:
        watch(args.interval)
        return
    process_once()


if __name__ == "__main__":
    main()
