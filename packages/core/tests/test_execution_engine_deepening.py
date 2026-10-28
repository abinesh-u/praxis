"""Regression test suite for Candidate 2: Deepened Execution Engine & ActionDispatcher seam."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from praxis_core.entities.common import (
    ActionRiskLevel,
    ApprovalStatus,
    TaskStatus,
)
from praxis_core.entities.task import Task
from praxis_core.errors import (
    InvalidApprovalError,
)
from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    RawDispatchResult,
)
from praxis_core.ports.status_reconciler import (
    RawReconcileResult,
    StatusReconciler,
)
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.execute_next_action import (
    ExecuteNextActionCommand,
    ExecuteNextActionUseCase,
)
from praxis_core.use_cases.reconcile_execution import (
    ReconcileExecutionCommand,
    ReconcileExecutionUseCase,
)


class RecordingDispatcher(ActionDispatcher):
    """Test dispatcher that records received DispatchSpec instances."""

    def __init__(self, result: RawDispatchResult | None = None) -> None:
        self.result = result or RawDispatchResult(status="completed", raw_payload={"success": True})
        self.received_specs: list[DispatchSpec] = []

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        self.received_specs.append(spec)
        return self.result


class RecordingReconciler(StatusReconciler):
    """Test reconciler that records status inspection invocations."""

    def __init__(self, result: RawReconcileResult | None = None) -> None:
        self.result = result or RawReconcileResult(status="outcome_unknown")
        self.inspections: list[dict[str, Any]] = []

    async def inspect_status(
        self,
        attempt_id: UUID,
        idempotency_key: str,
        provider_operation_id: str | None,
    ) -> RawReconcileResult:
        self.inspections.append(
            {
                "attempt_id": attempt_id,
                "idempotency_key": idempotency_key,
                "provider_operation_id": provider_operation_id,
            }
        )
        return self.result


# Gate 1: Pre-Dispatch Approval Halting
@pytest.mark.anyio
async def test_pre_dispatch_approval_halting_creates_no_running_attempt():
    uow = InMemoryUnitOfWork()
    task = Task(owner_id="user_1", title="Production Deploy")
    task.add_next_action("Deploy latest release", risk_level=ActionRiskLevel.CONSEQUENTIAL)

    dispatcher = RecordingDispatcher()
    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=dispatcher)

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="user_1")
    result = await use_case.execute(cmd)

    # Invariants:
    assert result.task.status == TaskStatus.AWAITING_APPROVAL
    assert result.approval_request is not None
    assert result.approval_token is not None
    assert result.attempt.status == "awaiting_approval"
    # Dispatcher was never invoked!
    assert len(dispatcher.received_specs) == 0


# Gate 2 & 3: Atomic Token Consumption and Invalid Token Rejection
@pytest.mark.anyio
async def test_atomic_token_consumption_and_invalid_token_rejection():
    uow = InMemoryUnitOfWork()
    task = Task(owner_id="user_1", title="Purge Cache")
    task.add_next_action("Delete all cache entries", risk_level=ActionRiskLevel.CONSEQUENTIAL)

    dispatcher = RecordingDispatcher()
    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=dispatcher)

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    # Step 1: Halt for approval to generate request and token
    halt_res = await use_case.execute(ExecuteNextActionCommand(task_id=task.id, owner_id="user_1"))
    token = halt_res.approval_token
    req = halt_res.approval_request

    # Step 2: Approve the request
    req.status = ApprovalStatus.APPROVED
    async with uow:
        await uow.approvals.save(req)
        await uow.commit()

    # Step 3: Presenting a wrong token fails and does NOT consume approval
    with pytest.raises(InvalidApprovalError):
        await use_case.execute(
            ExecuteNextActionCommand(
                task_id=task.id,
                owner_id="user_1",
                approval_token="wrong_token_secret",
            )
        )

    # Verify approval remains unconsumed
    async with uow:
        fresh_req = await uow.approvals.get_for_owner(req.id, "user_1")
        assert fresh_req.status == ApprovalStatus.APPROVED

    # Step 4: Presenting valid token consumes it and commits attempt before dispatch
    exec_res = await use_case.execute(
        ExecuteNextActionCommand(
            task_id=task.id,
            owner_id="user_1",
            approval_token=token,
        )
    )
    assert exec_res.attempt.status == "completed"
    assert len(dispatcher.received_specs) == 1

    # Verify approval is now CONSUMED
    async with uow:
        fresh_req = await uow.approvals.get_for_owner(req.id, "user_1")
        assert fresh_req.status == ApprovalStatus.CONSUMED


# Gate 4: Adapter Seam Decoupling
@pytest.mark.anyio
async def test_adapter_seam_receives_only_dispatch_spec():
    uow = InMemoryUnitOfWork()
    task = Task(owner_id="user_1", title="Routine Task")
    task.add_next_action("Check system status")

    dispatcher = RecordingDispatcher()
    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=dispatcher)

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    await use_case.execute(
        ExecuteNextActionCommand(
            task_id=task.id,
            owner_id="user_1",
            workspace_root="/tmp/test_workspace",
            idempotency_key="routine-101",
        )
    )

    assert len(dispatcher.received_specs) == 1
    spec = dispatcher.received_specs[0]

    # Invariant: DispatchSpec contains only primitive data, no domain entities
    assert isinstance(spec, DispatchSpec)
    assert spec.idempotency_key == "routine-101"
    assert spec.tool_name == "system_action"
    assert spec.destination_context["workspace_root"] == "/tmp/test_workspace"
    assert not hasattr(spec, "task")
    assert not hasattr(spec, "approval_token")


# Gate 5: Crash-Before-Dispatch Simulation and Recovery
@pytest.mark.anyio
async def test_crash_before_dispatch_recovery_prevents_duplicate_dispatch():
    uow = InMemoryUnitOfWork()
    task = Task(owner_id="user_1", title="Critical Action")
    action = task.add_next_action(
        "Execute financial wire", risk_level=ActionRiskLevel.CONSEQUENTIAL
    )

    dispatcher = RecordingDispatcher()
    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=dispatcher)

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    # Pre-authorize
    halt_res = await use_case.execute(ExecuteNextActionCommand(task_id=task.id, owner_id="user_1"))
    token = halt_res.approval_token
    halt_res.approval_request.status = ApprovalStatus.APPROVED
    async with uow:
        await uow.approvals.save(halt_res.approval_request)
        await uow.commit()

    # Simulate a crash right after Phase 1 commit by seeding an attempt in "running" status
    async with uow:
        task.status = TaskStatus.IN_PROGRESS
        from praxis_core.entities.execution_attempt import ExecutionAttempt

        crashed_attempt = ExecutionAttempt(
            owner_id="user_1",
            task_id=task.id,
            action_id=action.id,
            idempotency_key="wire-123",
            status="running",
        )
        await uow.attempts.save(crashed_attempt)
        await uow.tasks.save(task)
        await uow.commit()

    # Client retries with the same idempotency key after process restart
    retry_res = await use_case.execute(
        ExecuteNextActionCommand(
            task_id=task.id,
            owner_id="user_1",
            idempotency_key="wire-123",
            approval_token=token,
        )
    )

    # Invariant: The crashed attempt is returned as outcome_unknown for reconciliation;
    # NEVER blindly redispatched!
    assert retry_res.outcome.status == "outcome_unknown"
    assert len(dispatcher.received_specs) == 0


# Gate 6 & 9: Ambiguous / Malformed Receipt Must Remain outcome_unknown
@pytest.mark.anyio
async def test_ambiguous_or_unverified_receipt_remains_outcome_unknown():
    uow = InMemoryUnitOfWork()
    task = Task(owner_id="user_1", title="Webhook Operation")
    task.add_next_action("Dispatch provider webhook", tool_hint="webhook_post")

    # Dispatcher returns HTTP 200 payload, but status is "pending" (not "completed")
    pending_payload = {"status": "pending", "operation_id": "op-999"}
    ambiguous_result = RawDispatchResult(
        status="outcome_unknown",
        raw_payload=pending_payload,
        provider_operation_id="op-999",
    )
    dispatcher = RecordingDispatcher(result=ambiguous_result)
    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=dispatcher)

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    res = await use_case.execute(ExecuteNextActionCommand(task_id=task.id, owner_id="user_1"))

    # Invariant: Must remain outcome_unknown, not claimed as success or failure!
    assert res.attempt.status == "outcome_unknown"
    assert res.task.status == TaskStatus.IN_PROGRESS
    assert res.task.recovery_suggestion is not None


# Gate 7 & 8: Read-Only Reconciliation Guarantee
@pytest.mark.anyio
async def test_reconciliation_is_read_only_and_uses_status_reconciler():
    uow = InMemoryUnitOfWork()
    task = Task(owner_id="user_1", title="Reconcile Task")
    action = task.add_next_action("Notify remote service", tool_hint="webhook_post")

    async with uow:
        from praxis_core.entities.execution_attempt import ExecutionAttempt

        attempt = ExecutionAttempt(
            owner_id="user_1",
            task_id=task.id,
            action_id=action.id,
            idempotency_key="notify-888",
            status="outcome_unknown",
            provider_request_id="op-ext-888",
        )
        await uow.tasks.save(task)
        await uow.attempts.save(attempt)
        await uow.commit()

    reconciler = RecordingReconciler(
        result=RawReconcileResult(
            status="completed",
            raw_payload={"status": "completed", "operation_id": "op-ext-888"},
            provider_operation_id="op-ext-888",
        )
    )
    reconcile_use_case = ReconcileExecutionUseCase(uow=uow, reconciler=reconciler)

    result = await reconcile_use_case.execute(
        ReconcileExecutionCommand(
            task_id=task.id,
            attempt_id=attempt.id,
            owner_id="user_1",
        )
    )

    # Invariants:
    assert result.attempt.status == "completed"
    assert result.task.status == TaskStatus.COMPLETED
    assert len(reconciler.inspections) == 1
    assert reconciler.inspections[0]["provider_operation_id"] == "op-ext-888"
    assert reconciler.inspections[0]["idempotency_key"] == "notify-888"
