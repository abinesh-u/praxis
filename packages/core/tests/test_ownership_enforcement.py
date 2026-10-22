"""Unit tests verifying cross-tenant security and owner boundary enforcement."""

from datetime import UTC, datetime, timedelta

import pytest
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.complete_task import CompleteTaskCommand, CompleteTaskUseCase
from praxis_core.use_cases.defer_task import DeferTaskCommand, DeferTaskUseCase


class TestOwnershipEnforcement:
    """Verifies that repository queries strictly isolate entities by owner_id."""

    @pytest.mark.anyio
    async def test_complete_task_cross_tenant_denied(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_alice", title="Alice Task")
        task.start()

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        evidence = Evidence.machine_verified(
            target_task_id=task.id,
            verifier_identity="tool:check",
            details={},
        )

        use_case = CompleteTaskUseCase(uow=uow)
        # Attacker tries to complete Alice's task
        cmd = CompleteTaskCommand(
            task_id=task.id,
            owner_id="attacker_bob",
            evidence=evidence,
        )

        with pytest.raises(EntityNotFoundError):
            await use_case.execute(cmd)

    @pytest.mark.anyio
    async def test_defer_task_cross_tenant_denied(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_alice", title="Alice Task")

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        use_case = DeferTaskUseCase(uow=uow)
        cmd = DeferTaskCommand(
            task_id=task.id,
            owner_id="attacker_bob",
            until=datetime.now(UTC) + timedelta(days=1),
        )

        with pytest.raises(EntityNotFoundError):
            await use_case.execute(cmd)
