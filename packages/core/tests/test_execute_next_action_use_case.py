"""Unit tests for ExecuteNextActionUseCase."""

import pytest
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import (
    ActionRiskLevel,
    DependencyType,
    EvidenceSource,
    TaskStatus,
    VerificationStatus,
)
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import Task
from praxis_core.errors import BlockedTaskError, InvalidApprovalError
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.execute_next_action import (
    ExecuteNextActionCommand,
    ExecuteNextActionUseCase,
)
from praxis_core.use_cases.reconcile_execution import (
    ReconcileExecutionCommand,
    ReconcileExecutionUseCase,
)


class MockAgentRunner(AgentRunner):
    """Configurable mock runner for testing execution orchestrations."""

    def __init__(self, outcome: AgentRunOutcome | None = None) -> None:
        self.outcome = outcome or AgentRunOutcome(status="completed")
        self.invocations: list[dict] = []
        self.reconciliation_outcome = AgentRunOutcome(status="outcome_unknown")

    async def execute_action(
        self,
        attempt_id,
        task,
        action,
        owner_id,
        workspace_root=None,
        approval_token=None,
    ) -> AgentRunOutcome:
        self.invocations.append(
            {
                "attempt_id": attempt_id,
                "task_id": task.id,
                "action_id": action.id,
                "owner_id": owner_id,
            }
        )
        return self.outcome

    async def reconcile_action(
        self,
        attempt_id,
        task,
        action,
        owner_id,
        provider_request_id,
        idempotency_key,
    ) -> AgentRunOutcome:
        return self.reconciliation_outcome


class TestExecuteNextActionUseCase:
    """Verifies pre-execution persistence, runner coordination, and outcome reconciliation."""

    @pytest.mark.anyio
    async def test_blocked_task_raises_error_without_calling_runner(self):
        uow = InMemoryUnitOfWork()
        runner = MockAgentRunner()
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)

        prereq = Task(owner_id="user_1", title="Prereq")
        task = Task(owner_id="user_1", title="Dependent")
        task.add_dependency(prereq.id, DependencyType.BLOCKS)

        async with uow:
            await uow.tasks.save(prereq)
            await uow.tasks.save(task)
            await uow.commit()

        cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="user_1")
        with pytest.raises(BlockedTaskError):
            await use_case.execute(cmd)

        # Invariant: runner was never invoked
        assert len(runner.invocations) == 0

    @pytest.mark.anyio
    async def test_consequential_action_pauses_for_approval(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Deploy app")
        task.add_next_action("Delete stale build artifacts")

        action_spec = ActionSpecification(
            tool_name="workspace_fs.rm",
            canonical_args={"path": "/build/dist"},
            task_id=task.id,
        )
        outcome = AgentRunOutcome(
            status="awaiting_approval",
            action_spec=action_spec,
            approval_justification="Destructive file removal requires authorization",
        )
        runner = MockAgentRunner(outcome=outcome)
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="user_1")
        result = await use_case.execute(cmd)

        assert result.task.status == TaskStatus.AWAITING_APPROVAL
        assert result.approval_request is not None
        assert result.approval_request.action.tool_name == "workspace_fs.rm"
        assert result.attempt.status == "awaiting_approval"
        assert result.attempt.approval_id == result.approval_request.id

    @pytest.mark.anyio
    async def test_completed_with_evidence_completes_action_and_task(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Backup database")
        action = task.add_next_action("Export pg_dump to file")

        evidence = Evidence.machine_verified(
            target_task_id=task.id,
            target_action_id=action.id,
            verifier_identity="tool:pg_dump",
            details={"dump_size_bytes": 1048576},
        )
        outcome = AgentRunOutcome(
            status="completed",
            evidence=evidence,
        )
        runner = MockAgentRunner(outcome=outcome)
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="user_1")
        result = await use_case.execute(cmd)

        assert result.action.completed is True
        assert result.action.evidence_id == evidence.id
        assert result.task.status == TaskStatus.COMPLETED
        assert result.attempt.status == "completed"

    @pytest.mark.anyio
    async def test_completed_without_evidence_fails_task_and_attempt(self):
        """Invariant: An agent claiming completed without evidence triggers recovery failure."""
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Audit logs")
        task.add_next_action("Parse log events")

        unverified = Evidence(
            source=EvidenceSource.TOOL,
            verification_status=VerificationStatus.UNVERIFIED_ASSERTION,
            verifier_identity="unverified_agent",
            target_task_id=task.id,
            details={},
        )
        outcome = AgentRunOutcome(
            status="completed",
            evidence=unverified,
        )
        runner = MockAgentRunner(outcome=outcome)
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="user_1")
        result = await use_case.execute(cmd)

        # Invariant: Not completed! Fails with recovery suggestion
        assert result.task.status == TaskStatus.FAILED
        assert result.attempt.status == "failed"
        assert result.task.recovery_suggestion is not None

    @pytest.mark.anyio
    async def test_execute_next_action_idempotency_prevents_duplicate_tool_calls(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Export analytics")
        action = task.add_next_action("Run export script")

        evidence = Evidence.machine_verified(
            target_task_id=task.id,
            target_action_id=action.id,
            verifier_identity="tool:exporter",
            details={"rows": 500},
        )
        outcome = AgentRunOutcome(status="completed", evidence=evidence)
        runner = MockAgentRunner(outcome=outcome)
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        cmd = ExecuteNextActionCommand(
            task_id=task.id,
            owner_id="user_1",
            idempotency_key="export_job_001",
        )

        first_res = await use_case.execute(cmd)
        assert len(runner.invocations) == 1

        # Second call with same idempotency key
        second_res = await use_case.execute(cmd)
        # Invariant: Runner was NOT invoked a second time!
        assert len(runner.invocations) == 1
        assert second_res.attempt.id == first_res.attempt.id

    @pytest.mark.anyio
    async def test_uncertain_outcome_is_durable_and_never_retries_implicitly(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Notify provider")
        task.add_next_action("Send provider notification", tool_hint="webhook_post")
        runner = MockAgentRunner(
            AgentRunOutcome(
                status="outcome_unknown",
                error="Provider timed out after dispatch",
                provider_request_id="provider-op-1",
            )
        )
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        command = ExecuteNextActionCommand(
            task_id=task.id, owner_id="user_1", idempotency_key="notify-1"
        )
        first = await use_case.execute(command)
        second = await use_case.execute(command)

        assert first.attempt.status == "outcome_unknown"
        assert first.attempt.provider_request_id == "provider-op-1"
        assert second.outcome.status == "outcome_unknown"
        assert len(runner.invocations) == 1

    @pytest.mark.anyio
    async def test_missing_provider_id_gives_manual_recovery_guidance(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Provider without operation ID")
        task.add_next_action("Send provider notification", tool_hint="webhook_post")
        runner = MockAgentRunner(AgentRunOutcome(status="outcome_unknown"))
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        result = await use_case.execute(
            ExecuteNextActionCommand(task_id=task.id, owner_id="user_1", idempotency_key="no-id")
        )

        assert result.attempt.status == "outcome_unknown"
        assert result.attempt.provider_request_id is None
        assert "operation ID is unavailable" in (result.task.recovery_suggestion or "")
        assert "do not retry" in (result.task.recovery_suggestion or "")

    @pytest.mark.anyio
    async def test_reconciliation_observes_and_completes_without_dispatch(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Reconcile provider")
        action = task.add_next_action("Send provider notification", tool_hint="webhook_post")
        runner = MockAgentRunner(
            AgentRunOutcome(status="outcome_unknown", provider_request_id="op-1")
        )
        execute = ExecuteNextActionUseCase(uow=uow, runner=runner)
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()
        first = await execute.execute(
            ExecuteNextActionCommand(task_id=task.id, owner_id="user_1", idempotency_key="k1")
        )

        evidence = Evidence.machine_verified(
            target_task_id=task.id,
            target_action_id=action.id,
            verifier_identity="integration:webhook_post.reconcile",
            details={"status": "completed"},
        )
        runner.reconciliation_outcome = AgentRunOutcome(status="completed", evidence=evidence)
        reconciled = await ReconcileExecutionUseCase(uow=uow, runner=runner).execute(
            ReconcileExecutionCommand(
                task_id=task.id, attempt_id=first.attempt.id, owner_id="user_1"
            )
        )

        assert reconciled.attempt.status == "completed"
        assert reconciled.task.status == TaskStatus.COMPLETED
        assert len(runner.invocations) == 1

    @pytest.mark.anyio
    async def test_execute_next_action_fails_when_task_awaiting_approval(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Critical task")
        task.start()
        task.await_approval(reason="Requires human approval")

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        runner = MockAgentRunner()
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)

        cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="user_1")
        with pytest.raises(Exception) as exc_info:
            await use_case.execute(cmd)

        assert "awaiting_approval" in str(exc_info.value)
        assert len(runner.invocations) == 0

    @pytest.mark.anyio
    async def test_approved_action_requires_matching_one_time_token(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Delete archive")
        action = task.add_next_action(
            "Delete old archive", risk_level=ActionRiskLevel.CONSEQUENTIAL
        )
        request_runner = MockAgentRunner(
            AgentRunOutcome(
                status="awaiting_approval",
                action_spec=ActionSpecification(
                    tool_name="system_action",
                    canonical_args={"target": action.description},
                    task_id=task.id,
                    permission_scope="local_exec",
                ),
                approval_justification="Needs approval",
            )
        )
        use_case = ExecuteNextActionUseCase(uow=uow, runner=request_runner)

        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

        first = await use_case.execute(ExecuteNextActionCommand(task_id=task.id, owner_id="user_1"))
        assert first.approval_request is not None
        assert first.approval_token

        async with uow:
            approval = await uow.approvals.get_for_owner(first.approval_request.id, "user_1")
            stored_task = await uow.tasks.get_for_owner(task.id, "user_1")
            assert approval is not None and stored_task is not None
            approval.approve("user_1")
            stored_task.approval_granted()
            await uow.approvals.save(approval)
            await uow.tasks.save(stored_task)
            await uow.commit()

        completion = Evidence.machine_verified(
            target_task_id=task.id,
            target_action_id=action.id,
            verifier_identity="tool:archive",
            details={"deleted": True},
        )
        completion_runner = MockAgentRunner(
            AgentRunOutcome(status="completed", evidence=completion)
        )
        completed = await ExecuteNextActionUseCase(uow=uow, runner=completion_runner).execute(
            ExecuteNextActionCommand(
                task_id=task.id,
                owner_id="user_1",
                approval_token=first.approval_token,
            )
        )
        assert completed.task.status == TaskStatus.COMPLETED

        async with uow:
            consumed = await uow.approvals.get_for_owner(first.approval_request.id, "user_1")
            assert consumed is not None and consumed.status.value == "consumed"

    @pytest.mark.anyio
    async def test_wrong_token_is_rejected_before_runner_and_does_not_consume_approval(self):
        uow = InMemoryUnitOfWork()
        task = Task(owner_id="user_1", title="Delete archive")
        action = task.add_next_action(
            "Delete old archive", risk_level=ActionRiskLevel.CONSEQUENTIAL
        )
        action_spec = ActionSpecification(
            tool_name="system_action",
            canonical_args={"target": action.description},
            task_id=task.id,
            permission_scope="local_exec",
        )
        approval, token = ApprovalRequest.create(
            owner_id="user_1",
            task_id=task.id,
            action=action_spec,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Needs approval",
        )
        approval.approve("user_1")
        task.start()
        async with uow:
            await uow.tasks.save(task)
            await uow.approvals.save(approval)
            await uow.commit()

        runner = MockAgentRunner()
        use_case = ExecuteNextActionUseCase(uow=uow, runner=runner)
        with pytest.raises(InvalidApprovalError):
            await use_case.execute(
                ExecuteNextActionCommand(
                    task_id=task.id,
                    owner_id="user_1",
                    approval_token=f"{token}-tampered",
                )
            )
        assert runner.invocations == []

        async with uow:
            stored = await uow.approvals.get_for_owner(approval.id, "user_1")
            assert stored is not None and stored.status.value == "approved"
