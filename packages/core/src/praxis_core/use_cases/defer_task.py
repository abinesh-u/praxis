"""Use case for guilt-free task deferral and rescheduling."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError
from praxis_core.ports.unit_of_work import UnitOfWork


class DeferTaskCommand(BaseModel):
    """Command input for deferring a task."""

    task_id: UUID
    owner_id: str
    until: datetime
    reason: str | None = None


class DeferTaskUseCase:
    """Postpones a task without penalty, incrementing deferral count."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, cmd: DeferTaskCommand) -> Task:
        async with self.uow:
            task = await self.uow.tasks.get_for_owner(
                cmd.task_id,
                cmd.owner_id,
            )
            if task is None:
                raise EntityNotFoundError("Task", cmd.task_id)

            task.defer(until=cmd.until, reason=cmd.reason)

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

            return task
