"""Attempt repository port and in-memory test implementation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from praxis_core.entities.execution_attempt import ExecutionAttempt


class AttemptRepository(Protocol):
    """Abstract storage port for ExecutionAttempt records."""

    async def get(self, attempt_id: UUID) -> ExecutionAttempt | None:
        """Retrieve execution attempt by ID."""
        ...

    async def get_for_owner(self, attempt_id: UUID, owner_id: str) -> ExecutionAttempt | None:
        """Retrieve execution attempt strictly enforcing owner boundary."""
        ...

    async def save(self, attempt: ExecutionAttempt) -> ExecutionAttempt:
        """Persist or update execution attempt."""
        ...

    async def find_by_idempotency_key(
        self,
        key: str,
        owner_id: str,
    ) -> ExecutionAttempt | None:
        """Look up execution attempt by idempotency key and owner."""
        ...

    async def list_for_tasks(
        self,
        task_ids: list[UUID],
        owner_id: str,
    ) -> dict[UUID, list[ExecutionAttempt]]:
        """Return bounded attempt summaries grouped by owner-scoped task IDs."""
        ...


class InMemoryAttemptRepository:
    """In-memory attempt repository for testing."""

    def __init__(self) -> None:
        self._attempts: dict[UUID, ExecutionAttempt] = {}

    async def get(self, attempt_id: UUID) -> ExecutionAttempt | None:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            return None
        return attempt.model_copy(deep=True)

    async def get_for_owner(self, attempt_id: UUID, owner_id: str) -> ExecutionAttempt | None:
        attempt = self._attempts.get(attempt_id)
        if attempt is None or attempt.owner_id != owner_id:
            return None
        return attempt.model_copy(deep=True)

    async def save(self, attempt: ExecutionAttempt) -> ExecutionAttempt:
        self._attempts[attempt.id] = attempt.model_copy(deep=True)
        return attempt

    async def find_by_idempotency_key(
        self,
        key: str,
        owner_id: str,
    ) -> ExecutionAttempt | None:
        for attempt in self._attempts.values():
            if attempt.owner_id == owner_id and attempt.idempotency_key == key:
                return attempt.model_copy(deep=True)
        return None

    async def list_for_tasks(
        self, task_ids: list[UUID], owner_id: str
    ) -> dict[UUID, list[ExecutionAttempt]]:
        wanted = set(task_ids)
        grouped: dict[UUID, list[ExecutionAttempt]] = {task_id: [] for task_id in wanted}
        for attempt in self._attempts.values():
            if attempt.owner_id == owner_id and attempt.task_id in wanted:
                grouped[attempt.task_id].append(attempt.model_copy(deep=True))
        for attempts in grouped.values():
            attempts.sort(key=lambda value: value.started_at, reverse=True)
        return grouped
