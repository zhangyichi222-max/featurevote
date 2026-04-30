from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.clients.feishu import FeishuClient
from app.models.post import NotificationTaskModel, utc_now


class NotificationProcessor:
    def __init__(self, session: Session, feishu_client: FeishuClient | None = None) -> None:
        self.session = session
        self.feishu_client = feishu_client or FeishuClient()

    def process_pending(self, limit: int = 20) -> int:
        tasks = self._claim_pending(limit)
        processed = 0
        for task in tasks:
            self.process_task(task)
            self.session.commit()
            processed += 1
        return processed

    def _claim_pending(self, limit: int) -> list[NotificationTaskModel]:
        now = utc_now()
        stale_processing_at = now - timedelta(minutes=10)
        tasks = self.session.scalars(
            select(NotificationTaskModel)
            .where(
                NotificationTaskModel.attempts < NotificationTaskModel.max_attempts,
                (
                    (
                        (NotificationTaskModel.status == "pending")
                        & or_(
                            NotificationTaskModel.next_attempt_at.is_(None),
                            NotificationTaskModel.next_attempt_at <= now,
                        )
                    )
                    | (
                        (NotificationTaskModel.status == "processing")
                        & (NotificationTaskModel.updated_at <= stale_processing_at)
                    )
                ),
            )
            .order_by(NotificationTaskModel.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
        ).all()

        for task in tasks:
            task.status = "processing"
            task.updated_at = now
            self.session.add(task)
        self.session.commit()
        return list(tasks)

    def process_task(self, task: NotificationTaskModel) -> None:
        now = utc_now()
        if not task.recipient_open_id:
            task.status = "skipped"
            task.last_error = "Creator has no feishu_open_id."
            task.updated_at = now
            self.session.add(task)
            return

        try:
            self.feishu_client.send_text_message(task.recipient_open_id, task.message, uuid=task.id)
        except Exception as exc:  # noqa: BLE001 - notification failure must not escape processor loop.
            task.attempts += 1
            task.last_error = str(exc)
            task.updated_at = now
            if task.attempts >= task.max_attempts:
                task.status = "failed"
                task.next_attempt_at = None
            else:
                task.status = "pending"
                task.next_attempt_at = now + timedelta(minutes=task.attempts)
            self.session.add(task)
            return

        task.attempts += 1
        task.status = "sent"
        task.sent_at = now
        task.last_error = None
        task.next_attempt_at = None
        task.updated_at = now
        self.session.add(task)
