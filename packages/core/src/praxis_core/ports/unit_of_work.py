"""Unit of Work port governing transactional persistence boundaries."""

from __future__ import annotations

from typing import Protocol

from praxis_core.entities.task import Task
from praxis_core.ports.approval_repository import (
    ApprovalRepository,
    InMemoryApprovalRepository,
)
from praxis_core.ports.attempt_repository import (
    AttemptRepository,
    InMemoryAttemptRepository,
)
from praxis_core.ports.audit_sink import AuditSink, InMemoryAuditSink
from praxis_core.ports.commitment_repository import (
    CommitmentRepository,
    InMemoryCommitmentRepository,
)
from praxis_core.ports.task_repository import (
    InMemoryTaskRepository,
    TaskRepository,
)


class UnitOfWork(Protocol):
    """Coordinates atomic transactions across repositories and domain event dispatch."""

    tasks: TaskRepository
    commitments: CommitmentRepository
    approvals: ApprovalRepository
    attempts: AttemptRepository
    audit_sink: AuditSink

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None: ...

    async def commit(self) -> None:
        """Atomically persist state changes and dispatch recorded domain events."""
        ...

    async def rollback(self) -> None:
        """Discard uncommitted state changes."""
        ...


class InMemoryUnitOfWork:
    """In-memory Unit of Work implementation for unit tests."""

    def __init__(
        self,
        tasks: InMemoryTaskRepository | None = None,
        commitments: InMemoryCommitmentRepository | None = None,
        approvals: InMemoryApprovalRepository | None = None,
        attempts: InMemoryAttemptRepository | None = None,
        audit_sink: InMemoryAuditSink | None = None,
    ) -> None:
        self.tasks = tasks or InMemoryTaskRepository()
        self.commitments = commitments or InMemoryCommitmentRepository()
        self.approvals = approvals or InMemoryApprovalRepository()
        self.attempts = attempts or InMemoryAttemptRepository()
        self.audit_sink = audit_sink or InMemoryAuditSink()
        self._tracked_tasks: list[Task] = []
        self._committed = False

    def track_task(self, task: Task) -> None:
        """Track a task so its uncommitted domain events are dispatched on commit."""
        if task not in self._tracked_tasks:
            self._tracked_tasks.append(task)

    async def __aenter__(self) -> InMemoryUnitOfWork:
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        # Drain all domain events from tracked tasks and flush to audit sink
        for task in self._tracked_tasks:
            events = task.collect_events()
            if events:
                await self.audit_sink.record_all(events)
        self._tracked_tasks.clear()
        self._committed = True

    async def rollback(self) -> None:
        self._tracked_tasks.clear()
        self._committed = False
