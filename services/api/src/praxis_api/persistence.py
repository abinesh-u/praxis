"""Durable SQLite persistence adapters for the Praxis application ports.

The domain layer intentionally owns its entities and invariants.  This module
therefore persists canonical Pydantic JSON rather than duplicating every
aggregate field in an ORM model.  A few query fields are indexed separately so
owner-scoped lifecycle queries remain efficient and, crucially, cannot rely on
client-side filtering for isolation.

``DATABASE_URL`` currently supports SQLite URLs only.  PostgreSQL is an
intentional future adapter, rather than silently treating a PostgreSQL URL as a
local file.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import ApprovalStatus, TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from praxis_core.errors import ConcurrencyConflictError
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

EVENT_TYPE_MAP: dict[str, type[DomainEvent]] = {
    "task.created": TaskCreatedEvent,
    "task.status_changed": TaskStatusChangedEvent,
    "task.deferred": TaskDeferredEvent,
    "task.completed": TaskCompletedEvent,
    "task.failed": TaskFailedEvent,
    "approval.requested": ApprovalRequestedEvent,
    "approval.decided": ApprovalDecidedEvent,
}


class PersistenceConfigurationError(ValueError):
    """Raised when the configured database URL is unsupported or unsafe."""


class TransactionNotActiveError(RuntimeError):
    """Raised when a repository is used outside its Unit of Work scope."""


def database_url_from_environment() -> str:
    """Read the explicit service database configuration.

    A local file default keeps the service usable for development. Deployments
    should set ``DATABASE_URL`` explicitly (for example,
    ``sqlite:////var/lib/praxis/praxis.db``).
    """

    return os.environ.get("DATABASE_URL", "sqlite:///praxis.db")


def busy_timeout_ms_from_environment() -> int:
    """Read the configured SQLite busy timeout in milliseconds (default 5000ms)."""
    raw = os.environ.get("PRAXIS_SQLITE_BUSY_TIMEOUT_MS", "5000")
    try:
        val = int(raw)
        return max(500, min(val, 60_000))
    except ValueError:
        return 5000


@dataclass(frozen=True)
class Migration:
    """A single schema version step."""

    version: int
    description: str
    sql: str


# Ordered migration registry. Each entry advances the schema by one version.
MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Baseline schema with dedicated query and expression indexes",
        sql="""\
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL,
                due_at TEXT,
                scheduled_at TEXT,
                created_at TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS tasks_owner_status_idx ON tasks (owner_id, status);
            CREATE INDEX IF NOT EXISTS tasks_owner_schedule_idx
                ON tasks (owner_id, scheduled_at, due_at);
            CREATE INDEX IF NOT EXISTS tasks_owner_created_idx
                ON tasks (owner_id, created_at, id);
            CREATE INDEX IF NOT EXISTS tasks_owner_commitment_idx
                ON tasks (owner_id, json_extract(payload, '$.commitment_id'));
            CREATE INDEX IF NOT EXISTS tasks_owner_id_idx
                ON tasks (owner_id, id);

            CREATE TABLE IF NOT EXISTS commitments (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                idempotency_key TEXT,
                captured_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (owner_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS commitments_owner_captured_idx
                ON commitments (owner_id, captured_at, id);

            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS approvals_owner_status_idx
                ON approvals (owner_id, status, expires_at);

            CREATE TABLE IF NOT EXISTS execution_attempts (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (owner_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS attempts_owner_task_idx
                ON execution_attempts (owner_id, task_id, id);

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS audit_events_aggregate_idx
                ON audit_events (aggregate_id, occurred_at, event_id);
        """,
    ),
]

SCHEMA_VERSION = MIGRATIONS[-1].version


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    """Create the migration tracking table if it does not exist."""
    connection.execute(
        """\
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _current_schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or 0 if none."""
    row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


REQUIRED_TABLE_COLUMNS: dict[str, set[str]] = {
    "tasks": {"id", "owner_id", "status", "version", "payload"},
    "commitments": {"id", "owner_id", "idempotency_key", "captured_at", "payload"},
    "approvals": {"id", "owner_id", "task_id", "status", "expires_at", "payload"},
    "execution_attempts": {
        "id",
        "owner_id",
        "task_id",
        "action_id",
        "idempotency_key",
        "status",
        "payload",
    },
    "audit_events": {
        "event_id",
        "owner_id",
        "aggregate_id",
        "event_type",
        "occurred_at",
        "payload",
    },
}


def _verify_legacy_schema_fingerprint(connection: sqlite3.Connection) -> bool:
    """Verify legacy database contains all expected baseline tables and required columns."""
    tables = {
        r[0]
        for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if not set(REQUIRED_TABLE_COLUMNS.keys()).issubset(tables):
        return False
    for table_name, expected_cols in REQUIRED_TABLE_COLUMNS.items():
        actual_cols = {
            r["name"] for r in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if not expected_cols.issubset(actual_cols):
            return False
    return True


def _apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply any unapplied migrations in order within transactional boundaries."""
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        raise PersistenceConfigurationError(f"Database lock acquisition timed out: {exc}") from exc

    try:
        _ensure_migration_table(connection)
        current = _current_schema_version(connection)

        # Legacy baseline detection (version 0 with pre-existing tables)
        if current == 0:
            table_check = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchone()
            if table_check is not None:
                if not _verify_legacy_schema_fingerprint(connection):
                    raise PersistenceConfigurationError(
                        "Legacy database schema does not match expected baseline format"
                    )
                connection.executescript(MIGRATIONS[0].sql)
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version, description, applied_at) "
                    "VALUES (?, ?, ?)",
                    (1, "Baseline legacy schema", datetime.now(UTC).isoformat()),
                )
                current = 1

        for migration in MIGRATIONS:
            if migration.version <= current:
                continue
            connection.executescript(migration.sql)
            connection.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.description, datetime.now(UTC).isoformat()),
            )

        connection.commit()
    except BaseException as exc:
        connection.rollback()
        if isinstance(exc, PersistenceConfigurationError):
            raise
        raise PersistenceConfigurationError(f"Failed to apply database migration: {exc}") from exc


def schema_version(database_url: str) -> int:
    """Return the current schema version of the given database URL."""
    path = sqlite_path_from_url(database_url)
    timeout_ms = busy_timeout_ms_from_environment()
    connection = sqlite3.connect(path, timeout=timeout_ms / 1000.0)
    connection.row_factory = sqlite3.Row
    try:
        _ensure_migration_table(connection)
        return _current_schema_version(connection)
    finally:
        connection.close()


def sqlite_path_from_url(database_url: str) -> str:
    """Convert a SQLite URL to a sqlite3 path without accepting other dialects."""

    if database_url == "sqlite:///:memory:":
        return ":memory:"
    if not database_url.startswith("sqlite:///"):
        raise PersistenceConfigurationError(
            "DATABASE_URL must be a SQLite URL such as sqlite:///praxis.db; "
            "PostgreSQL requires a dedicated adapter."
        )

    path = database_url.removeprefix("sqlite:///")
    if not path:
        raise PersistenceConfigurationError("SQLite DATABASE_URL must include a database path")
    # sqlite:////absolute/path becomes /absolute/path after removing sqlite:///.
    return path


def _payload(model: Any) -> str:
    return model.model_dump_json()


def _task_from_payload(payload: str) -> Task:
    task = Task.model_validate_json(payload)
    # Hydration must not manufacture a TaskCreated event for version-one tasks.
    task.collect_events()
    return task


def _event_from_payload(payload: str) -> DomainEvent:
    data = json.loads(payload)
    event_type = data.get("event_type", "")
    return EVENT_TYPE_MAP.get(event_type, DomainEvent).model_validate(data)


class _SQLiteRepository:
    def __init__(self, uow: SQLiteUnitOfWork) -> None:
        self._uow = uow

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._uow._require_connection()


class SQLiteTaskRepository(_SQLiteRepository):
    async def get(self, task_id: UUID) -> Task | None:
        row = self._connection.execute(
            "SELECT payload FROM tasks WHERE id = ?", (str(task_id),)
        ).fetchone()
        return _task_from_payload(row["payload"]) if row else None

    async def get_for_owner(self, task_id: UUID, owner_id: str) -> Task | None:
        row = self._connection.execute(
            "SELECT payload FROM tasks WHERE id = ? AND owner_id = ?", (str(task_id), owner_id)
        ).fetchone()
        return _task_from_payload(row["payload"]) if row else None

    async def save(self, task: Task, expected_version: int | None = None) -> Task:
        existing = self._connection.execute(
            "SELECT version FROM tasks WHERE id = ?", (str(task.id),)
        ).fetchone()
        if existing is not None and expected_version is not None:
            actual_version = int(existing["version"])
            if actual_version != expected_version:
                raise ConcurrencyConflictError(task.id, expected_version, actual_version)

        self._connection.execute(
            """
            INSERT INTO tasks (
                id, owner_id, status, version, due_at, scheduled_at, created_at, payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_id = excluded.owner_id,
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
                task.scheduled_date.isoformat() if task.scheduled_date else None,
                task.created_at.isoformat(),
                _payload(task),
            ),
        )
        return task

    async def list_active_for_today(self, date: datetime, owner_id: str) -> list[Task]:
        # Datetimes are compared by the aggregate to preserve the core's exact
        # timezone semantics rather than depending on SQLite date coercion.
        rows = self._connection.execute(
            "SELECT payload FROM tasks WHERE owner_id = ? AND status NOT IN (?, ?)",
            (owner_id, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value),
        ).fetchall()
        date_only = date.date()
        result: list[Task] = []
        for row in rows:
            task = _task_from_payload(row["payload"])
            scheduled_due = task.scheduled_date and task.scheduled_date.date() <= date_only
            deadline_due = task.due_date and task.due_date.date() <= date_only
            if (
                scheduled_due
                or deadline_due
                or task.status
                in {
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.DEFERRED,
                    TaskStatus.AWAITING_APPROVAL,
                    TaskStatus.FAILED,
                }
                or (task.scheduled_date is None and task.due_date is None)
            ):
                result.append(task)
        return result

    async def list_by_status(
        self, status: TaskStatus, owner_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        effective_limit = max(1, min(limit, 1000))
        effective_offset = max(0, offset)
        rows = self._connection.execute(
            "SELECT payload FROM tasks WHERE owner_id = ? AND status = ? "
            "ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?",
            (owner_id, status.value, effective_limit, effective_offset),
        ).fetchall()
        return [_task_from_payload(row["payload"]) for row in rows]

    async def list_by_owner(
        self, owner_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        effective_limit = max(1, min(limit, 1000))
        effective_offset = max(0, offset)
        rows = self._connection.execute(
            "SELECT payload FROM tasks WHERE owner_id = ? "
            "ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?",
            (owner_id, effective_limit, effective_offset),
        ).fetchall()
        return [_task_from_payload(row["payload"]) for row in rows]

    async def find_by_commitment_id(self, commitment_id: UUID, owner_id: str) -> Task | None:
        row = self._connection.execute(
            "SELECT payload FROM tasks WHERE owner_id = ? "
            "AND json_extract(payload, '$.commitment_id') = ?",
            (owner_id, str(commitment_id)),
        ).fetchone()
        return _task_from_payload(row["payload"]) if row else None

    async def count_by_status(self, owner_id: str) -> dict[TaskStatus, int]:
        rows = self._connection.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks WHERE owner_id = ? GROUP BY status",
            (owner_id,),
        ).fetchall()
        counts = dict.fromkeys(TaskStatus, 0)
        for row in rows:
            try:
                counts[TaskStatus(row["status"])] = int(row["cnt"])
            except ValueError:
                continue
        return counts

    async def find_by_id_prefix(self, prefix: str, owner_id: str) -> list[Task]:
        clean = prefix.strip().lower().replace("-", "")
        rows = self._connection.execute(
            "SELECT payload FROM tasks WHERE owner_id = ? AND id LIKE (? || '%') ORDER BY id ASC",
            (owner_id, clean),
        ).fetchall()
        return [_task_from_payload(row["payload"]) for row in rows]


class SQLiteCommitmentRepository(_SQLiteRepository):
    async def get(self, commitment_id: UUID) -> Commitment | None:
        row = self._connection.execute(
            "SELECT payload FROM commitments WHERE id = ?", (str(commitment_id),)
        ).fetchone()
        return Commitment.model_validate_json(row["payload"]) if row else None

    async def get_for_owner(self, commitment_id: UUID, owner_id: str) -> Commitment | None:
        row = self._connection.execute(
            "SELECT payload FROM commitments WHERE id = ? AND owner_id = ?",
            (str(commitment_id), owner_id),
        ).fetchone()
        return Commitment.model_validate_json(row["payload"]) if row else None

    async def save(self, commitment: Commitment) -> Commitment:
        self._connection.execute(
            """
            INSERT INTO commitments (id, owner_id, idempotency_key, captured_at, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_id = excluded.owner_id,
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
        return commitment

    async def list_by_owner(self, owner_id: str) -> list[Commitment]:
        rows = self._connection.execute(
            "SELECT payload FROM commitments WHERE owner_id = ? ORDER BY captured_at", (owner_id,)
        ).fetchall()
        return [Commitment.model_validate_json(row["payload"]) for row in rows]

    async def find_by_idempotency_key(self, key: str, owner_id: str) -> Commitment | None:
        row = self._connection.execute(
            "SELECT payload FROM commitments WHERE owner_id = ? AND idempotency_key = ?",
            (owner_id, key),
        ).fetchone()
        return Commitment.model_validate_json(row["payload"]) if row else None


class SQLiteApprovalRepository(_SQLiteRepository):
    async def get(self, approval_id: UUID) -> ApprovalRequest | None:
        row = self._connection.execute(
            "SELECT payload FROM approvals WHERE id = ?", (str(approval_id),)
        ).fetchone()
        return ApprovalRequest.model_validate_json(row["payload"]) if row else None

    async def get_for_owner(self, approval_id: UUID, owner_id: str) -> ApprovalRequest | None:
        row = self._connection.execute(
            "SELECT payload FROM approvals WHERE id = ? AND owner_id = ?",
            (str(approval_id), owner_id),
        ).fetchone()
        return ApprovalRequest.model_validate_json(row["payload"]) if row else None

    async def save(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._connection.execute(
            """
            INSERT INTO approvals (id, owner_id, task_id, status, expires_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_id = excluded.owner_id,
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
        return approval

    async def list_pending(self, owner_id: str) -> list[ApprovalRequest]:
        rows = self._connection.execute(
            "SELECT payload FROM approvals WHERE owner_id = ? AND status = ? ORDER BY expires_at",
            (owner_id, ApprovalStatus.PENDING.value),
        ).fetchall()
        return [ApprovalRequest.model_validate_json(row["payload"]) for row in rows]

    async def list_for_task(self, task_id: UUID, owner_id: str) -> list[ApprovalRequest]:
        rows = self._connection.execute(
            "SELECT payload FROM approvals WHERE task_id = ? AND owner_id = ? ORDER BY expires_at",
            (str(task_id), owner_id),
        ).fetchall()
        return [ApprovalRequest.model_validate_json(row["payload"]) for row in rows]


class SQLiteAttemptRepository(_SQLiteRepository):
    async def get(self, attempt_id: UUID) -> ExecutionAttempt | None:
        row = self._connection.execute(
            "SELECT payload FROM execution_attempts WHERE id = ?", (str(attempt_id),)
        ).fetchone()
        return ExecutionAttempt.model_validate_json(row["payload"]) if row else None

    async def get_for_owner(self, attempt_id: UUID, owner_id: str) -> ExecutionAttempt | None:
        row = self._connection.execute(
            "SELECT payload FROM execution_attempts WHERE id = ? AND owner_id = ?",
            (str(attempt_id), owner_id),
        ).fetchone()
        return ExecutionAttempt.model_validate_json(row["payload"]) if row else None

    async def save(self, attempt: ExecutionAttempt) -> ExecutionAttempt:
        self._connection.execute(
            """
            INSERT INTO execution_attempts (
                id, owner_id, task_id, action_id, idempotency_key, status, payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_id = excluded.owner_id,
                task_id = excluded.task_id,
                action_id = excluded.action_id,
                idempotency_key = excluded.idempotency_key,
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
        return attempt

    async def find_by_idempotency_key(self, key: str, owner_id: str) -> ExecutionAttempt | None:
        row = self._connection.execute(
            "SELECT payload FROM execution_attempts WHERE owner_id = ? AND idempotency_key = ?",
            (owner_id, key),
        ).fetchone()
        return ExecutionAttempt.model_validate_json(row["payload"]) if row else None

    async def list_for_tasks(
        self, task_ids: list[UUID], owner_id: str, *, limit_per_task: int = 10
    ) -> dict[UUID, list[ExecutionAttempt]]:
        grouped: dict[UUID, list[ExecutionAttempt]] = {task_id: [] for task_id in task_ids}
        if not task_ids:
            return grouped
        placeholders = ",".join("?" for _ in task_ids)
        rows = self._connection.execute(
            f"SELECT payload FROM execution_attempts WHERE owner_id = ? "
            f"AND task_id IN ({placeholders}) ORDER BY id DESC",
            (owner_id, *(str(task_id) for task_id in task_ids)),
        ).fetchall()
        for row in rows:
            attempt = ExecutionAttempt.model_validate_json(row["payload"])
            grouped.setdefault(attempt.task_id, []).append(attempt)
        effective_limit = max(1, min(limit_per_task, 100))
        for task_id in grouped:
            grouped[task_id].sort(key=lambda value: (value.started_at, str(value.id)), reverse=True)
            grouped[task_id] = grouped[task_id][:effective_limit]
        return grouped


class SQLiteAuditSink(_SQLiteRepository):
    async def record(self, event: DomainEvent) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO audit_events (
                event_id, owner_id, aggregate_id, event_type, occurred_at, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id),
                event.owner_id,
                str(event.aggregate_id),
                event.event_type,
                event.occurred_at.isoformat(),
                _payload(event),
            ),
        )

    async def record_all(self, events: list[DomainEvent]) -> None:
        for event in events:
            await self.record(event)

    async def list_for_aggregate(
        self, aggregate_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[DomainEvent]:
        effective_limit = max(1, min(limit, 5000))
        effective_offset = max(0, offset)
        rows = self._connection.execute(
            "SELECT payload FROM audit_events "
            "WHERE aggregate_id = ? ORDER BY occurred_at ASC, event_id ASC LIMIT ? OFFSET ?",
            (str(aggregate_id), effective_limit, effective_offset),
        ).fetchall()
        return [_event_from_payload(row["payload"]) for row in rows]


class SQLiteUnitOfWork:
    """Transactional SQLite implementation of Praxis's UnitOfWork port.

    Each async context owns one connection and transaction.  The instance is
    intentionally reusable across requests/use-case calls, but repositories may
    only be used while its context is active.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or database_url_from_environment()
        self._database_path = sqlite_path_from_url(self.database_url)
        self._busy_timeout_ms = busy_timeout_ms_from_environment()
        self._connection: sqlite3.Connection | None = None
        self._tracked_tasks: list[Task] = []

        self._initialize_schema()
        self.tasks = SQLiteTaskRepository(self)
        self.commitments = SQLiteCommitmentRepository(self)
        self.approvals = SQLiteApprovalRepository(self)
        self.attempts = SQLiteAttemptRepository(self)
        self.audit_sink = SQLiteAuditSink(self)

    def _connect(self) -> sqlite3.Connection:
        if self._database_path != ":memory:":
            db_path = Path(self._database_path).expanduser()
            if not db_path.parent.exists():
                db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with contextlib.suppress(OSError):
                    db_path.parent.chmod(0o700)
            if not db_path.exists():
                db_path.touch(mode=0o600, exist_ok=True)
                with contextlib.suppress(OSError):
                    db_path.chmod(0o600)

        timeout_seconds = self._busy_timeout_ms / 1000.0
        connection = sqlite3.connect(
            self._database_path,
            isolation_level=None,
            check_same_thread=False,
            timeout=timeout_seconds,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if self._database_path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        return connection

    def _initialize_schema(self) -> None:
        connection = self._connect()
        try:
            _apply_migrations(connection)
        finally:
            connection.close()

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise TransactionNotActiveError(
                "Use repositories within 'async with SQLiteUnitOfWork(...)'"
            )
        return self._connection

    def track_task(self, task: Task) -> None:
        if task not in self._tracked_tasks:
            self._tracked_tasks.append(task)

    async def __aenter__(self) -> SQLiteUnitOfWork:
        if self._connection is not None:
            raise RuntimeError("SQLiteUnitOfWork does not support nested transactions")
        self._connection = self._connect()
        self._connection.execute("BEGIN IMMEDIATE")
        return self

    async def commit(self) -> None:
        connection = self._require_connection()
        tracked = list(self._tracked_tasks)
        events: list[DomainEvent] = []
        for task in tracked:
            events.extend(task.collect_events())
        try:
            if events:
                await self.audit_sink.record_all(events)
            connection.commit()
            self._tracked_tasks.clear()
            # Keep a transaction open for callers that make additional changes
            # before leaving the same Unit of Work scope.
            connection.execute("BEGIN IMMEDIATE")
        except BaseException:
            connection.rollback()
            for task, task_events in _events_by_task(tracked, events):
                task._events.extend(task_events)  # noqa: SLF001 - preserves uncommitted domain events
            raise

    async def rollback(self) -> None:
        connection = self._require_connection()
        connection.rollback()
        self._tracked_tasks.clear()
        connection.execute("BEGIN IMMEDIATE")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            # Explicit commit is required: avoiding implicit persistence makes
            # interrupted workflows observable and recoverable.
            connection.rollback()
            if exc_type is not None:
                self._tracked_tasks.clear()
        finally:
            connection.close()
            self._connection = None


def _events_by_task(
    tasks: list[Task], events: list[DomainEvent]
) -> Iterator[tuple[Task, list[DomainEvent]]]:
    """Associate drained events with their aggregate if a commit must be retried."""

    for task in tasks:
        yield task, [event for event in events if event.aggregate_id == task.id]


# ``Sqlite`` is retained as a convenient spelling for callers while the
# all-caps class name mirrors the standard library's SQLite terminology.
SqliteUnitOfWork = SQLiteUnitOfWork
