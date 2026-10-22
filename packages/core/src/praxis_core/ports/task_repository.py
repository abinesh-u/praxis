"""Task repository port and in-memory test implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from praxis_core.entities.common import TaskStatus
from praxis_core.entities.task import Task
from praxis_core.errors import ConcurrencyConflictError


class TaskRepository(Protocol):
    """Abstract storage port for Task aggregates."""

    async def get(self, task_id: UUID) -> Task | None:
        """Retrieve task by ID."""
        ...

    async def get_for_owner(self, task_id: UUID, owner_id: str) -> Task | None:
        """Retrieve task by ID strictly enforcing owner boundary."""
        ...

    async def save(self, task: Task, expected_version: int | None = None) -> Task:
        """Save task aggregate with optimistic concurrency check."""
        ...

    async def list_active_for_today(self, date: datetime, owner_id: str) -> list[Task]:
        """List tasks scheduled for or due on today that are not yet completed/cancelled."""
        ...

    async def list_by_status(self, status: TaskStatus, owner_id: str) -> list[Task]:
        """List tasks for an owner matching a specific lifecycle status."""
        ...

    async def list_by_owner(self, owner_id: str) -> list[Task]:
        """List all tasks belonging to an owner."""
        ...


class InMemoryTaskRepository:
    """Thread-safe in-memory task repository for testing and local prototypes."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, Task] = {}

    async def get(self, task_id: UUID) -> Task | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.model_copy(deep=True)

    async def get_for_owner(self, task_id: UUID, owner_id: str) -> Task | None:
        task = self._tasks.get(task_id)
        if task is None or task.owner_id != owner_id:
            return None
        return task.model_copy(deep=True)

    async def save(self, task: Task, expected_version: int | None = None) -> Task:
        existing = self._tasks.get(task.id)
        if (
            existing is not None
            and expected_version is not None
            and existing.version != expected_version
        ):
            raise ConcurrencyConflictError(task.id, expected_version, existing.version)

        self._tasks[task.id] = task.model_copy(deep=True)
        return task

    async def list_active_for_today(self, date: datetime, owner_id: str) -> list[Task]:
        date_only = date.date()
        result: list[Task] = []
        for task in self._tasks.values():
            if task.owner_id != owner_id:
                continue
            if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                continue

            scheduled_due = task.scheduled_date and task.scheduled_date.date() <= date_only
            deadline_due = task.due_date and task.due_date.date() <= date_only
            in_progress = task.status == TaskStatus.IN_PROGRESS

            if scheduled_due or deadline_due or in_progress:
                result.append(task.model_copy(deep=True))
        return result

    async def list_by_status(self, status: TaskStatus, owner_id: str) -> list[Task]:
        return [
            t.model_copy(deep=True)
            for t in self._tasks.values()
            if t.owner_id == owner_id and t.status == status
        ]

    async def list_by_owner(self, owner_id: str) -> list[Task]:
        return [t.model_copy(deep=True) for t in self._tasks.values() if t.owner_id == owner_id]
