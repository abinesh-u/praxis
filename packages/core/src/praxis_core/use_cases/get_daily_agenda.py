"""Use case for retrieving today's prioritized agenda with actionable and waiting sections."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.common import DependencyType, Priority, TaskStatus
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.ports.clock import Clock, SystemClock
from praxis_core.ports.unit_of_work import UnitOfWork

PRIORITY_SORT_WEIGHT = {
    Priority.URGENT: 0,
    Priority.IMPORTANT: 1,
    Priority.ROUTINE: 2,
}


class AgendaTaskItem(BaseModel):
    """A task presentation model with immediate next action and blocker status."""

    task: Task
    current_next_action: NextAction | None = None
    is_blocked: bool = False
    waiting_reason: str | None = None


class DailyAgendaResult(BaseModel):
    """The structured Daily Agenda dividing obligations into actionable vs waiting."""

    date: datetime
    actionable: list[AgendaTaskItem]
    waiting: list[AgendaTaskItem]


class GetDailyAgendaUseCase:
    """Builds an actionable-first agenda, keeping cognitive load calm and low-friction."""

    def __init__(self, uow: UnitOfWork, clock: Clock | None = None) -> None:
        self.uow = uow
        self.clock = clock or SystemClock()

    async def execute(self, owner_id: str, date: datetime | None = None) -> DailyAgendaResult:
        target_date = date or self.clock.now()

        async with self.uow:
            tasks = await self.uow.tasks.list_active_for_today(target_date, owner_id)

            actionable_items: list[AgendaTaskItem] = []
            waiting_items: list[AgendaTaskItem] = []

            for task in tasks:
                next_action = task.get_current_next_action()

                if task.status == TaskStatus.AWAITING_APPROVAL:
                    waiting_items.append(
                        AgendaTaskItem(
                            task=task,
                            current_next_action=next_action,
                            is_blocked=True,
                            waiting_reason="Waiting for user authorization on tool action",
                        )
                    )
                    continue

                if task.status == TaskStatus.FAILED:
                    reason = task.failure_reason or "Execution failed"
                    waiting_items.append(
                        AgendaTaskItem(
                            task=task,
                            current_next_action=next_action,
                            is_blocked=True,
                            waiting_reason=f"Action failed: {reason} (requires retry or replan)",
                        )
                    )
                    continue

                if task.status == TaskStatus.DEFERRED:
                    until_str = (
                        task.deferred_until.isoformat() if task.deferred_until else "future date"
                    )
                    waiting_items.append(
                        AgendaTaskItem(
                            task=task,
                            current_next_action=next_action,
                            is_blocked=True,
                            waiting_reason=f"Deferred until {until_str}",
                        )
                    )
                    continue

                # Check blocking dependencies
                blocking_ids: list[UUID] = []
                for dep in task.dependencies:
                    if dep.dependency_type == DependencyType.BLOCKS:
                        prereq = await self.uow.tasks.get_for_owner(
                            dep.depends_on_task_id,
                            owner_id,
                        )
                        if prereq is None or prereq.status != TaskStatus.COMPLETED:
                            blocking_ids.append(dep.depends_on_task_id)

                if blocking_ids:
                    waiting_items.append(
                        AgendaTaskItem(
                            task=task,
                            current_next_action=next_action,
                            is_blocked=True,
                            waiting_reason=f"Blocked by {len(blocking_ids)} prerequisite task(s)",
                        )
                    )
                else:
                    actionable_items.append(
                        AgendaTaskItem(
                            task=task,
                            current_next_action=next_action,
                            is_blocked=False,
                        )
                    )

            # Deterministic sorting for actionable: Urgent -> Important -> Routine, then due date
            def sort_key(item: AgendaTaskItem):
                p_weight = PRIORITY_SORT_WEIGHT.get(item.task.priority, 3)
                due_ts = item.task.due_date.timestamp() if item.task.due_date else float("inf")
                created_ts = item.task.created_at.timestamp()
                return (p_weight, due_ts, created_ts)

            actionable_items.sort(key=sort_key)

            return DailyAgendaResult(
                date=target_date,
                actionable=actionable_items,
                waiting=waiting_items,
            )
