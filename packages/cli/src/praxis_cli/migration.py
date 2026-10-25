"""Migration helper to transparently transition legacy JSON store files to SQLite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from praxis_core.events import (
    ApprovalDecidedEvent,
    ApprovalRequestedEvent,
    DomainEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskDeferredEvent,
    TaskFailedEvent,
    TaskStatusChangedEvent,
)
from praxis_core.persistence.sqlite import (
    SQLiteUnitOfWork,
    _apply_migrations,
    sqlite_path_from_url,
)

logger = logging.getLogger(__name__)

EVENT_TYPE_MAP: dict[str, type[DomainEvent]] = {
    "task.created": TaskCreatedEvent,
    "task.status_changed": TaskStatusChangedEvent,
    "task.deferred": TaskDeferredEvent,
    "task.completed": TaskCompletedEvent,
    "task.failed": TaskFailedEvent,
    "approval.requested": ApprovalRequestedEvent,
    "approval.decided": ApprovalDecidedEvent,
}


def _payload(model: Any) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return json.dumps(model)


class JsonStoreMigrator:
    """Migrates legacy store.json data into the unified SQLite persistence engine."""

    @classmethod
    def migrate_sync(cls, json_path: Path, database_url: str) -> bool:
        """Synchronously migrate legacy store.json to SQLite database if it exists."""
        if not json_path.exists():
            return False

        try:
            content = json_path.read_text(encoding="utf-8").strip()
        except OSError as err:
            logger.warning("Failed to read legacy store at %s: %s", json_path, err)
            return False

        if not content:
            cls._archive_legacy_file(json_path)
            return False

        try:
            data: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError as err:
            logger.error("Corrupted JSON store encountered at %s: %s", json_path, err)
            raise ValueError(f"Cannot migrate corrupted JSON store at {json_path}: {err}") from err

        if not isinstance(data, dict):
            return False

        tasks_data = data.get("tasks", {})
        commitments_data = data.get("commitments", {})
        approvals_data = data.get("approvals", {})
        attempts_data = data.get("attempts", {})
        audit_events_data = data.get("audit_events", [])

        db_path = sqlite_path_from_url(database_url)
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        conn = sqlite3.connect(
            db_path,
            isolation_level=None,
            check_same_thread=False,
            timeout=10.0,
        )
        try:
            conn.row_factory = sqlite3.Row
            _apply_migrations(conn)

            conn.execute("BEGIN IMMEDIATE")
            try:
                # 1. Commitments
                if isinstance(commitments_data, dict):
                    for raw_commitment in commitments_data.values():
                        if isinstance(raw_commitment, dict):
                            commitment = Commitment.model_validate(raw_commitment)
                            conn.execute(
                                """
                                INSERT INTO commitments (
                                    id, owner_id, idempotency_key, captured_at, payload
                                )
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT (id) DO UPDATE SET
                                    idempotency_key = excluded.idempotency_key,
                                    captured_at = excluded.captured_at,
                                    payload = excluded.payload
                                """,
                                (
                                    str(commitment.id),
                                    commitment.owner_id,
                                    commitment.idempotency_key,
                                    commitment.captured_at.isoformat(),
                                    _payload(commitment),
                                ),
                            )

                # 2. Tasks
                if isinstance(tasks_data, dict):
                    for raw_task in tasks_data.values():
                        if isinstance(raw_task, dict):
                            task = Task.model_validate(raw_task)
                            conn.execute(
                                """
                                INSERT INTO tasks (
                                    id, owner_id, status, version,
                                    due_at, scheduled_at, created_at, payload
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT (id) DO UPDATE SET
                                    status = excluded.status,
                                    version = excluded.version,
                                    due_at = excluded.due_at,
                                    scheduled_at = excluded.scheduled_at,
                                    created_at = excluded.created_at,
                                    payload = excluded.payload
                                """,
                                (
                                    str(task.id),
                                    task.owner_id,
                                    task.status.value,
                                    task.version,
                                    task.due_date.isoformat() if task.due_date else None,
                                    task.scheduled_date.isoformat()
                                    if task.scheduled_date
                                    else None,
                                    task.created_at.isoformat(),
                                    _payload(task),
                                ),
                            )

                # 3. Approvals
                if isinstance(approvals_data, dict):
                    for raw_approval in approvals_data.values():
                        if isinstance(raw_approval, dict):
                            approval = ApprovalRequest.model_validate(raw_approval)
                            conn.execute(
                                """
                                INSERT INTO approvals (
                                    id, owner_id, task_id, status, expires_at, payload
                                )
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT (id) DO UPDATE SET
                                    task_id = excluded.task_id,
                                    status = excluded.status,
                                    expires_at = excluded.expires_at,
                                    payload = excluded.payload
                                """,
                                (
                                    str(approval.id),
                                    approval.owner_id,
                                    str(approval.task_id),
                                    approval.status.value,
                                    approval.expires_at.isoformat(),
                                    _payload(approval),
                                ),
                            )

                # 4. Attempts
                if isinstance(attempts_data, dict):
                    for raw_attempt in attempts_data.values():
                        if isinstance(raw_attempt, dict):
                            attempt = ExecutionAttempt.model_validate(raw_attempt)
                            conn.execute(
                                """
                                INSERT INTO execution_attempts (
                                    id, owner_id, task_id, action_id,
                                    idempotency_key, status, payload
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT (id) DO UPDATE SET
                                    status = excluded.status,
                                    payload = excluded.payload
                                """,
                                (
                                    str(attempt.id),
                                    attempt.owner_id,
                                    str(attempt.task_id),
                                    str(attempt.action_id),
                                    attempt.idempotency_key,
                                    attempt.status,
                                    _payload(attempt),
                                ),
                            )

                # 5. Audit events
                if isinstance(audit_events_data, list):
                    for raw_event in audit_events_data:
                        if isinstance(raw_event, dict):
                            event_type = raw_event.get("event_type")
                            cls_type = EVENT_TYPE_MAP.get(str(event_type))
                            if cls_type:
                                try:
                                    event = cls_type.model_validate(raw_event)
                                    conn.execute(
                                        """
                                        INSERT INTO audit_events (
                                            event_id, event_type, aggregate_id,
                                            owner_id, occurred_at, payload
                                        )
                                        VALUES (?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            str(event.event_id),
                                            event.event_type,
                                            str(event.aggregate_id),
                                            event.owner_id,
                                            event.occurred_at.isoformat(),
                                            _payload(event),
                                        ),
                                    )
                                except Exception:
                                    pass
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        finally:
            conn.close()

        cls._archive_legacy_file(json_path)
        return True

    @classmethod
    async def migrate_if_needed(cls, json_path: Path, uow: SQLiteUnitOfWork) -> bool:
        """Asynchronously migrate legacy store.json to SQLite database."""
        return cls.migrate_sync(json_path, uow.database_url)

    @staticmethod
    def _archive_legacy_file(json_path: Path) -> None:
        """Rename store.json to store.json.migrated and remove legacy lockfile."""
        migrated_path = json_path.with_name(f"{json_path.name}.migrated")
        try:
            if json_path.exists():
                os.replace(json_path, migrated_path)
            lock_path = json_path.with_suffix(".lock")
            if lock_path.exists():
                lock_path.unlink(missing_ok=True)
            logger.info("Migrated legacy store from %s to %s", json_path, migrated_path)
        except OSError as err:
            logger.warning("Failed to archive legacy store file %s: %s", json_path, err)
