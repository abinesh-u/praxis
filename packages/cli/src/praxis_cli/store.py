"""JSON file-backed persistence engine for local-first CLI operation.

Implements sidecar locking and directory fsync for POSIX crash durability.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import logging
import os
import time
import uuid
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
from praxis_core.ports.approval_repository import ApprovalRepository
from praxis_core.ports.attempt_repository import AttemptRepository
from praxis_core.ports.audit_sink import AuditSink
from praxis_core.ports.commitment_repository import CommitmentRepository
from praxis_core.ports.task_repository import TaskRepository

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


class StorageError(Exception):
    """Base exception for CLI storage failures."""


class StorageLockTimeoutError(StorageError):
    """Raised when the exclusive sidecar lock cannot be acquired within timeout."""


class CorruptStorageError(StorageError):
    """Raised when the storage file exists but cannot be deserialized or validated."""


class TransactionError(StorageError):
    """Raised when transactional operations are attempted outside an active transaction."""


class JsonTaskRepository(TaskRepository):
    """Task aggregate repository backed by in-memory dictionary loaded from JSON."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}

    def load(self, data: dict[str, Any]) -> None:
        self._tasks = {k: v for k, v in data.items() if isinstance(v, dict)}

    def dump(self) -> dict[str, Any]:
        return dict(self._tasks)

    async def get(self, task_id: UUID) -> Task | None:
        raw = self._tasks.get(str(task_id))
        return Task.model_validate(raw) if raw else None

    async def get_for_owner(self, task_id: UUID, owner_id: str) -> Task | None:
        raw = self._tasks.get(str(task_id))
        if raw is None or raw.get("owner_id") != owner_id:
            return None
        return Task.model_validate(raw)

    async def save(self, task: Task, expected_version: int | None = None) -> Task:
        key = str(task.id)
        existing = self._tasks.get(key)
        if existing is not None and expected_version is not None:
            actual_version = existing.get("version", 1)
            if actual_version != expected_version:
                raise ConcurrencyConflictError(task.id, expected_version, actual_version)

        # Increment version for optimistic locking on update
        if existing is not None:
            task.version = existing.get("version", 1) + 1

        self._tasks[key] = json.loads(task.model_dump_json())
        return task

    async def list_active_for_today(self, date: datetime, owner_id: str) -> list[Task]:
        date_only = date.date()
        result: list[Task] = []
        for raw in self._tasks.values():
            if raw.get("owner_id") != owner_id:
                continue
            status = raw.get("status")
            if status in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
                continue

            scheduled_raw = raw.get("scheduled_date")
            due_raw = raw.get("due_date")
            is_in_progress = status == TaskStatus.IN_PROGRESS.value
            is_deferred = status == TaskStatus.DEFERRED.value
            is_awaiting_approval = status == TaskStatus.AWAITING_APPROVAL.value
            is_failed = status == TaskStatus.FAILED.value
            is_unscheduled = scheduled_raw is None and due_raw is None

            sched_due = (
                datetime.fromisoformat(scheduled_raw).date() <= date_only
                if scheduled_raw
                else False
            )
            dead_due = datetime.fromisoformat(due_raw).date() <= date_only if due_raw else False

            if (
                sched_due
                or dead_due
                or is_in_progress
                or is_deferred
                or is_awaiting_approval
                or is_failed
                or is_unscheduled
            ):
                result.append(Task.model_validate(raw))
        return result

    async def list_by_status(self, status: TaskStatus, owner_id: str) -> list[Task]:
        return [
            Task.model_validate(raw)
            for raw in self._tasks.values()
            if raw.get("owner_id") == owner_id and raw.get("status") == status.value
        ]

    async def list_by_owner(self, owner_id: str) -> list[Task]:
        return [
            Task.model_validate(raw)
            for raw in self._tasks.values()
            if raw.get("owner_id") == owner_id
        ]


class JsonCommitmentRepository(CommitmentRepository):
    """Commitment repository backed by JSON storage."""

    def __init__(self) -> None:
        self._commitments: dict[str, dict[str, Any]] = {}

    def load(self, data: dict[str, Any]) -> None:
        self._commitments = {k: v for k, v in data.items() if isinstance(v, dict)}

    def dump(self) -> dict[str, Any]:
        return dict(self._commitments)

    async def get(self, commitment_id: UUID) -> Commitment | None:
        raw = self._commitments.get(str(commitment_id))
        return Commitment.model_validate(raw) if raw else None

    async def get_for_owner(self, commitment_id: UUID, owner_id: str) -> Commitment | None:
        raw = self._commitments.get(str(commitment_id))
        if raw is None or raw.get("owner_id") != owner_id:
            return None
        return Commitment.model_validate(raw)

    async def save(self, commitment: Commitment) -> Commitment:
        key = str(commitment.id)
        self._commitments[key] = json.loads(commitment.model_dump_json())
        return commitment

    async def find_by_idempotency_key(self, key: str, owner_id: str) -> Commitment | None:
        for raw in self._commitments.values():
            if raw.get("owner_id") == owner_id and raw.get("idempotency_key") == key:
                return Commitment.model_validate(raw)
        return None


class JsonApprovalRepository(ApprovalRepository):
    """ApprovalRequest repository backed by JSON storage."""

    def __init__(self) -> None:
        self._approvals: dict[str, dict[str, Any]] = {}

    def load(self, data: dict[str, Any]) -> None:
        self._approvals = {k: v for k, v in data.items() if isinstance(v, dict)}

    def dump(self) -> dict[str, Any]:
        return dict(self._approvals)

    async def get(self, approval_id: UUID) -> ApprovalRequest | None:
        raw = self._approvals.get(str(approval_id))
        return ApprovalRequest.model_validate(raw) if raw else None

    async def get_for_owner(self, approval_id: UUID, owner_id: str) -> ApprovalRequest | None:
        raw = self._approvals.get(str(approval_id))
        if raw is None or raw.get("owner_id") != owner_id:
            return None
        return ApprovalRequest.model_validate(raw)

    async def save(self, approval: ApprovalRequest) -> ApprovalRequest:
        key = str(approval.id)
        self._approvals[key] = json.loads(approval.model_dump_json())
        return approval

    async def list_pending(self, owner_id: str) -> list[ApprovalRequest]:
        return [
            ApprovalRequest.model_validate(raw)
            for raw in self._approvals.values()
            if raw.get("owner_id") == owner_id and raw.get("status") == ApprovalStatus.PENDING.value
        ]

    async def list_for_task(self, task_id: UUID, owner_id: str) -> list[ApprovalRequest]:
        task_id_str = str(task_id)
        return [
            ApprovalRequest.model_validate(raw)
            for raw in self._approvals.values()
            if raw.get("owner_id") == owner_id and raw.get("task_id") == task_id_str
        ]


class JsonAttemptRepository(AttemptRepository):
    """ExecutionAttempt repository backed by JSON storage."""

    def __init__(self) -> None:
        self._attempts: dict[str, dict[str, Any]] = {}

    def load(self, data: dict[str, Any]) -> None:
        self._attempts = {k: v for k, v in data.items() if isinstance(v, dict)}

    def dump(self) -> dict[str, Any]:
        return dict(self._attempts)

    async def get(self, attempt_id: UUID) -> ExecutionAttempt | None:
        raw = self._attempts.get(str(attempt_id))
        return ExecutionAttempt.model_validate(raw) if raw else None

    async def get_for_owner(self, attempt_id: UUID, owner_id: str) -> ExecutionAttempt | None:
        raw = self._attempts.get(str(attempt_id))
        if raw is None or raw.get("owner_id") != owner_id:
            return None
        return ExecutionAttempt.model_validate(raw)

    async def save(self, attempt: ExecutionAttempt) -> ExecutionAttempt:
        key = str(attempt.id)
        self._attempts[key] = json.loads(attempt.model_dump_json())
        return attempt

    async def find_by_idempotency_key(self, key: str, owner_id: str) -> ExecutionAttempt | None:
        for raw in self._attempts.values():
            if raw.get("owner_id") == owner_id and raw.get("idempotency_key") == key:
                return ExecutionAttempt.model_validate(raw)
        return None

    async def list_for_tasks(
        self, task_ids: list[UUID], owner_id: str
    ) -> dict[UUID, list[ExecutionAttempt]]:
        wanted = set(task_ids)
        grouped: dict[UUID, list[ExecutionAttempt]] = {task_id: [] for task_id in wanted}
        for raw in self._attempts.values():
            if raw.get("owner_id") != owner_id:
                continue
            attempt = ExecutionAttempt.model_validate(raw)
            if attempt.task_id in wanted:
                grouped[attempt.task_id].append(attempt)
        for attempts in grouped.values():
            attempts.sort(key=lambda value: value.started_at, reverse=True)
        return grouped

    async def list_for_task(self, task_id: UUID, owner_id: str) -> list[ExecutionAttempt]:
        tid_str = str(task_id)
        return [
            ExecutionAttempt.model_validate(raw)
            for raw in self._attempts.values()
            if raw.get("owner_id") == owner_id and raw.get("task_id") == tid_str
        ]


class JsonAuditSink(AuditSink):
    """AuditSink recording domain events to JSON storage."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def load(self, data: list[dict[str, Any]]) -> None:
        self._events = list(data)

    def dump(self) -> list[dict[str, Any]]:
        return list(self._events)

    async def record(self, event: DomainEvent) -> None:
        self._events.append(json.loads(event.model_dump_json()))

    async def record_all(self, events: list[DomainEvent]) -> None:
        for ev in events:
            self._events.append(json.loads(ev.model_dump_json()))

    async def list_for_aggregate(self, aggregate_id: UUID) -> list[DomainEvent]:
        agg_str = str(aggregate_id)
        results: list[DomainEvent] = []
        for raw in self._events:
            if raw.get("aggregate_id") == agg_str:
                etype = raw.get("event_type", "")
                cls = EVENT_TYPE_MAP.get(etype, DomainEvent)
                results.append(cls.model_validate(raw))
        return results


class JsonFileUnitOfWork:
    """ACID-compliant, sidecar-locked JSON persistence engine with directory fsync.

    Security & Reliability invariants:
    1. Static sidecar lockfile (`store.lock`) prevents inode invalidation during atomic replacement.
    2. Lock acquired *before* reading or creating `store.json`.
    3. Writes to temp file in same directory with 0o600 permissions, calls f.flush() + os.fsync().
    4. Atomic rename via os.replace() followed immediately by directory fsync (parent directory).
    5. Clean rollback semantics discarding uncommitted in-memory mutations.
    """

    SCHEMA_VERSION = 1

    def __init__(self, store_path: Path, lock_timeout_seconds: float = 5.0) -> None:
        self.store_path = store_path
        self.lock_path = store_path.with_suffix(".lock")
        self.lock_timeout = lock_timeout_seconds
        self._lock_fd: int | None = None
        self._tracked_tasks: list[Task] = []
        self._in_transaction = False

        self.tasks = JsonTaskRepository()
        self.commitments = JsonCommitmentRepository()
        self.approvals = JsonApprovalRepository()
        self.attempts = JsonAttemptRepository()
        self.audit_sink = JsonAuditSink()

    def track_task(self, task: Task) -> None:
        """Track a task so uncommitted domain events are dispatched on commit."""
        if task not in self._tracked_tasks:
            self._tracked_tasks.append(task)

    async def __aenter__(self) -> JsonFileUnitOfWork:
        # 1. Ensure profile directory exists with private permissions (0o700)
        self.store_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # 2. Open static sidecar lockfile with 0o600 permissions
        self._lock_fd = os.open(
            str(self.lock_path),
            os.O_CREAT | os.O_RDWR,
            0o600,
        )

        # 3. Acquire exclusive non-blocking lock with bounded retry
        start_time = time.monotonic()
        while True:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError) as err:
                if time.monotonic() - start_time >= self.lock_timeout:
                    os.close(self._lock_fd)
                    self._lock_fd = None
                    msg = f"Database is locked by another process ({self.lock_timeout:.1f}s)."
                    raise StorageLockTimeoutError(msg) from err
                await asyncio.sleep(0.05)

        # 4. Load store from disk while holding lock
        self._load_store()
        self._in_transaction = True
        return self

    def _create_empty_store(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "updated_at": datetime.now(UTC).isoformat(),
            "tasks": {},
            "commitments": {},
            "approvals": {},
            "attempts": {},
            "audit_events": [],
        }

    def _load_store(self) -> None:
        if not self.store_path.exists():
            data = self._create_empty_store()
        else:
            try:
                content = self.store_path.read_text(encoding="utf-8")
                if not content.strip():
                    data = self._create_empty_store()
                else:
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise CorruptStorageError("Storage root must be a JSON object.")
                    if data.get("schema_version") != self.SCHEMA_VERSION:
                        data = self._migrate_schema(data)
            except (json.JSONDecodeError, OSError) as err:
                raise CorruptStorageError(f"Storage file corrupted: {err}") from err

        self.tasks.load(data.get("tasks", {}))
        self.commitments.load(data.get("commitments", {}))
        self.approvals.load(data.get("approvals", {}))
        self.attempts.load(data.get("attempts", {}))
        self.audit_sink.load(data.get("audit_events", []))

    def _migrate_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        # Migration hook for future schema versions
        data["schema_version"] = self.SCHEMA_VERSION
        return data

    async def commit(self) -> None:
        if not self._in_transaction:
            raise TransactionError("Cannot commit outside an active transaction.")

        # Dispatch domain events to audit sink before serializing
        for task in self._tracked_tasks:
            events = task.collect_events()
            if events:
                await self.audit_sink.record_all(events)
        self._tracked_tasks.clear()

        # Build payload
        now_utc = datetime.now(datetime.UTC if hasattr(datetime, "UTC") else None)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "updated_at": now_utc.isoformat(),
            "tasks": self.tasks.dump(),
            "commitments": self.commitments.dump(),
            "approvals": self.approvals.dump(),
            "attempts": self.attempts.dump(),
            "audit_events": self.audit_sink.dump(),
        }

        # Write to isolated temp file in the same directory (same filesystem mount)
        tmp_path = self.store_path.with_name(
            f"{self.store_path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
        )
        try:
            fd = os.open(str(tmp_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename while lock is held
            os.replace(str(tmp_path), str(self.store_path))

            # Directory fsync: commit directory inode pointer to durable storage
            dir_fd = os.open(str(self.store_path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()

    async def rollback(self) -> None:
        self._tracked_tasks.clear()
        self._load_store()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            self._in_transaction = False
            if self._lock_fd is not None:
                try:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                    os.close(self._lock_fd)
                except OSError:
                    pass
                self._lock_fd = None
