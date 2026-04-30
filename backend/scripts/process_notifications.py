from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.notifications import NotificationProcessor


def main() -> None:
    with SessionLocal() as session:
        processed = NotificationProcessor(session).process_pending()
    print(f"Processed {processed} notification task(s).")


if __name__ == "__main__":
    main()
