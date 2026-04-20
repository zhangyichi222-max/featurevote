import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.schemas.requirement import RequirementCreate, RequirementItem, VoteCreate


class RequirementsRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    async def list_requirements(self) -> list[RequirementItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, req_id, title, description, status, vote_count,
                       creator_name, creator_open_id, created_at, updated_at
                FROM requirements
                ORDER BY created_at DESC
                """
            ).fetchall()

        return [
            RequirementItem(
                id=row["id"],
                req_id=row["req_id"],
                title=row["title"],
                description=row["description"],
                status=row["status"],
                vote_count=row["vote_count"],
                creator_name=row["creator_name"],
                creator_open_id=row["creator_open_id"],
                created_at=_parse_datetime(row["created_at"]),
                updated_at=_parse_datetime(row["updated_at"]),
            )
            for row in rows
        ]

    async def create_requirement(self, payload: RequirementCreate) -> dict:
        now = _utc_now_isoformat()
        record_id = uuid4().hex
        req_id = f"REQ-{uuid4().hex[:8].upper()}"

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO requirements (
                    id, req_id, title, description, status, vote_count,
                    creator_name, creator_open_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    req_id,
                    payload.title,
                    payload.description,
                    "backlog",
                    0,
                    payload.creator_name,
                    payload.creator_open_id,
                    now,
                    now,
                ),
            )
            connection.commit()

        return {
            "record_id": record_id,
            "fields": {
                "req_id": req_id,
                "title": payload.title,
                "description": payload.description,
                "status": "backlog",
                "vote_count": 0,
                "creator_name": payload.creator_name,
                "creator_open_id": payload.creator_open_id,
                "created_at": now,
                "updated_at": now,
            },
        }

    async def create_vote(self, requirement_id: str, payload: VoteCreate) -> dict:
        vote_id = uuid4().hex
        created_at = _utc_now_isoformat()

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO votes (id, requirement_id, voter_open_id, voter_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    vote_id,
                    requirement_id,
                    payload.voter_open_id,
                    payload.voter_name,
                    created_at,
                ),
            )
            connection.commit()

        return {
            "record_id": vote_id,
            "fields": {
                "requirement_id": requirement_id,
                "voter_open_id": payload.voter_open_id,
                "voter_name": payload.voter_name,
                "created_at": created_at,
            },
        }

    async def list_votes(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, requirement_id, voter_open_id, voter_name, created_at
                FROM votes
                ORDER BY created_at DESC
                """
            ).fetchall()

        return [
            {
                "record_id": row["id"],
                "fields": {
                    "requirement_id": row["requirement_id"],
                    "voter_open_id": row["voter_open_id"],
                    "voter_name": row["voter_name"],
                    "created_at": row["created_at"],
                },
            }
            for row in rows
        ]

    async def update_requirement(self, record_id: str, fields: dict) -> dict:
        allowed_fields = {"status", "vote_count"}
        updates = {key: value for key, value in fields.items() if key in allowed_fields}
        updates["updated_at"] = _utc_now_isoformat()

        assignments = ", ".join(f"{column} = ?" for column in updates)
        parameters = [*updates.values(), record_id]

        with self._lock, self._connect() as connection:
            connection.execute(
                f"""
                UPDATE requirements
                SET {assignments}
                WHERE id = ?
                """,
                parameters,
            )
            row = connection.execute(
                """
                SELECT id, req_id, title, description, status, vote_count,
                       creator_name, creator_open_id, created_at, updated_at
                FROM requirements
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()
            connection.commit()

        return {
            "record_id": row["id"],
            "fields": {
                "req_id": row["req_id"],
                "title": row["title"],
                "description": row["description"],
                "status": row["status"],
                "vote_count": row["vote_count"],
                "creator_name": row["creator_name"],
                "creator_open_id": row["creator_open_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        }

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS requirements (
                    id TEXT PRIMARY KEY,
                    req_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    vote_count INTEGER NOT NULL DEFAULT 0,
                    creator_name TEXT NOT NULL,
                    creator_open_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS votes (
                    id TEXT PRIMARY KEY,
                    requirement_id TEXT NOT NULL,
                    voter_open_id TEXT NOT NULL,
                    voter_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(requirement_id, voter_open_id),
                    FOREIGN KEY(requirement_id) REFERENCES requirements(id)
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
