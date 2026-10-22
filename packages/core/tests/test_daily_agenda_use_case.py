"""Unit tests for GetDailyAgendaUseCase."""

from datetime import UTC, datetime, timedelta

import pytest
from praxis_core.entities.common import DependencyType, Priority
from praxis_core.entities.task import Task
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.get_daily_agenda import GetDailyAgendaUseCase


class TestGetDailyAgendaUseCase:
    """Verifies actionable vs waiting partitioning and deterministic prioritization."""

    @pytest.mark.anyio
    async def test_agenda_divides_actionable_and_waiting_deterministically(self):
        uow = InMemoryUnitOfWork()
        now = datetime.now(UTC)

        # 1. Actionable Urgent Task
        t_urgent = Task(
            owner_id="user_1",
            title="Fix production outage",
            priority=Priority.URGENT,
            due_date=now + timedelta(hours=2),
            scheduled_date=now,
        )
        t_urgent.add_next_action("Check kubernetes logs")

        # 2. Actionable Routine Task
        t_routine = Task(
            owner_id="user_1",
            title="Clean desk",
            priority=Priority.ROUTINE,
            scheduled_date=now,
        )
        t_routine.add_next_action("Wipe down monitor")

        # 3. Blocked Task (waiting on t_urgent)
        t_blocked = Task(
            owner_id="user_1",
            title="Deploy release v2",
            priority=Priority.IMPORTANT,
            scheduled_date=now,
        )
        t_blocked.add_dependency(t_urgent.id, DependencyType.BLOCKS)

        # 4. Awaiting Approval Task
        t_approval = Task(
            owner_id="user_1",
            title="Drop staging database",
            priority=Priority.ROUTINE,
            scheduled_date=now,
        )
        t_approval.start()
        t_approval.await_approval(reason="Drop database needs approval")

        # 5. Deferred Task
        t_deferred = Task(
            owner_id="user_1",
            title="Prepare tax forms",
            priority=Priority.IMPORTANT,
            scheduled_date=now,
        )
        t_deferred.defer(until=now + timedelta(days=2))

        # 6. Failed Task (needs retry)
        t_failed = Task(
            owner_id="user_1",
            title="Sync S3 bucket",
            priority=Priority.ROUTINE,
            scheduled_date=now,
        )
        t_failed.start()
        t_failed.fail("Network timeout")

        # 7. Other user task (must be excluded)
        t_other = Task(
            owner_id="other_user",
            title="Other user secret task",
            scheduled_date=now,
        )

        async with uow:
            await uow.tasks.save(t_urgent)
            await uow.tasks.save(t_routine)
            await uow.tasks.save(t_blocked)
            await uow.tasks.save(t_approval)
            await uow.tasks.save(t_deferred)
            await uow.tasks.save(t_failed)
            await uow.tasks.save(t_other)
            await uow.commit()

        use_case = GetDailyAgendaUseCase(uow=uow)
        agenda = await use_case.execute(owner_id="user_1", date=now)

        # Actionable must only contain unblocked ready tasks
        assert len(agenda.actionable) == 2
        # URGENT task must be first
        assert agenda.actionable[0].task.id == t_urgent.id
        assert agenda.actionable[0].current_next_action.description == "Check kubernetes logs"
        # ROUTINE task second
        assert agenda.actionable[1].task.id == t_routine.id

        # Waiting must contain blocked, awaiting approval, deferred, and failed
        assert len(agenda.waiting) == 4
        waiting_task_ids = [w.task.id for w in agenda.waiting]
        assert t_blocked.id in waiting_task_ids
        assert t_approval.id in waiting_task_ids
        assert t_deferred.id in waiting_task_ids
        assert t_failed.id in waiting_task_ids

        # Other user's task was excluded
        assert t_other.id not in [a.task.id for a in agenda.actionable]
        assert t_other.id not in waiting_task_ids
