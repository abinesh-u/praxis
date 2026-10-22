"""Use case for explicitly completing a task with verified evidence."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.common import TaskStatus
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError
from praxis_core.ports.unit_of_work import UnitOfWork


class CompleteTaskCommand(BaseModel):
    """Command input for completing a task."""

    task_id: UUID
    owner_id: str
    evidence: Evidence


class CompleteTaskUseCase:
    """Verifies evidence and marks task complete within an atomic transaction."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, cmd: CompleteTaskCommand) -> Task:
        async with self.uow:
            task = await self.uow.tasks.get_for_owner(
                cmd.task_id,
                cmd.owner_id,
            )
            if task is None:
                raise EntityNotFoundError("Task", cmd.task_id)

            # Idempotent replay: if already completed with this exact evidence, return task
            if task.status == TaskStatus.COMPLETED and cmd.evidence.id in task.evidence_records:
                return task

            if task.status == TaskStatus.PLANNED:
                task.start()

            task.complete(cmd.evidence)

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

            return task
