from pathlib import Path
import argparse
import sys
import time

from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.notifications import NotificationProcessor


def process_once() -> int:
    with SessionLocal() as session:
        processed = NotificationProcessor(session).process_pending()
    if processed:
        print(f"Processed {processed} notification task(s).", flush=True)
    return processed


def watch(interval: float) -> None:
    print(f"Watching notification tasks every {interval:g} second(s).", flush=True)
    while True:
        try:
            process_once()
        except OperationalError as exc:
            print(f"Notification polling database error: {exc}", flush=True)
        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending Feishu notification tasks.")
    parser.add_argument("--watch", action="store_true", help="Keep polling pending notification tasks.")
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
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
