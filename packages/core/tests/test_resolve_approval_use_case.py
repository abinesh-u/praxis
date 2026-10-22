"""Unit tests for ResolveApprovalUseCase."""

import pytest
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus, TaskStatus
from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.resolve_approval import (
    ResolveApprovalCommand,
    ResolveApprovalUseCase,
)


@pytest.fixture
def setup_pending_approval():
    task = Task(owner_id="user_1", title="Consequential Task")
    task.start()
    task.await_approval(reason="File removal requires confirmation")

    action_spec = ActionSpecification(
        tool_name="workspace_fs.rm",
        canonical_args={"path": "/tmp/test"},
        task_id=task.id,
    )
    req, _ = ApprovalRequest.create(
        owner_id="user_1",
        task_id=task.id,
        action=action_spec,
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="File removal",
    )
    return task, req


class TestResolveApprovalUseCase:
    """Verifies approval decision handling and task status synchronization."""

    @pytest.mark.anyio
    async def test_approve_resumes_task_to_in_progress(self, setup_pending_approval):
        task, req = setup_pending_approval
        uow = InMemoryUnitOfWork()

        async with uow:
            await uow.tasks.save(task)
            await uow.approvals.save(req)
            await uow.commit()

        use_case = ResolveApprovalUseCase(uow=uow)
        cmd = ResolveApprovalCommand(
            approval_id=req.id,
            owner_id="user_1",
            decision="approve",
        )
        result = await use_case.execute(cmd)

        assert result.approval.status == ApprovalStatus.APPROVED
        assert result.task.status == TaskStatus.IN_PROGRESS

    @pytest.mark.anyio
    async def test_reject_reverts_task_to_planned(self, setup_pending_approval):
        task, req = setup_pending_approval
        uow = InMemoryUnitOfWork()

        async with uow:
            await uow.tasks.save(task)
            await uow.approvals.save(req)
            await uow.commit()

        use_case = ResolveApprovalUseCase(uow=uow)
        cmd = ResolveApprovalCommand(
            approval_id=req.id,
            owner_id="user_1",
            decision="reject",
            rejection_reason="Do not delete this file yet",
            fatal_rejection=False,
        )
        result = await use_case.execute(cmd)

        assert result.approval.status == ApprovalStatus.REJECTED
        assert result.task.status == TaskStatus.PLANNED

    @pytest.mark.anyio
    async def test_resolve_approval_wrong_owner_raises_not_found(self, setup_pending_approval):
        task, req = setup_pending_approval
        uow = InMemoryUnitOfWork()

        async with uow:
            await uow.tasks.save(task)
            await uow.approvals.save(req)
            await uow.commit()

        use_case = ResolveApprovalUseCase(uow=uow)
        cmd = ResolveApprovalCommand(
            approval_id=req.id,
            owner_id="attacker_user",  # Wrong owner
            decision="approve",
        )
        with pytest.raises(EntityNotFoundError):
            await use_case.execute(cmd)
