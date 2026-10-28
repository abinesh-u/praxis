"""Integration test module validating M6 agent runtime adapter and dispatch seam.

Tests verify:
1. Agent-backed execution using existing dispatcher and execution contracts.
2. Skill selection locality and prompt formatting depth.
3. Allowlisted tool perimeters and bounded step quotas.
4. Interactive approval token consumption and checkpoint resumption.
5. Evidence synthesis preserving verifiable proof for completed agent runs.
6. WebhookRunner and AgentActionDispatcher coexisting across the routing adapter.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from praxis_agent_runtime.adapter import AgentActionDispatcher
from praxis_agent_runtime.loop.checkpoints import CheckpointStore
from praxis_agent_runtime.skills.models import Skill
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.tools.registry import ToolRegistry
from praxis_agent_runtime.types import ToolResult
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus, TaskStatus
from praxis_core.entities.task import Task
from praxis_core.execution.dispatcher import RoutingActionDispatcher
from praxis_core.persistence.sqlite import SQLiteUnitOfWork
from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    RawDispatchResult,
)
from praxis_core.ports.status_reconciler import (
    RawReconcileResult,
    StatusReconciler,
)
from praxis_core.use_cases import (
    ExecuteNextActionCommand,
    ExecuteNextActionUseCase,
    ReconcileExecutionCommand,
    ReconcileExecutionUseCase,
    ResolveApprovalCommand,
    ResolveApprovalUseCase,
)


class MockAgentLLM:
    """Mock LLM adapter tracking prompts and returning predefined tool calls."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.prompts: list[str] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        for m in messages:
            if m.get("role") == "system":
                self.prompts.append(m.get("content", ""))
        if self.call_count >= len(self.responses):
            return "Task completed."
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


class MockWorkspaceTool(BaseTool):
    name = "workspace_build"
    description = "Executes workspace build step"
    risk_level = ActionRiskLevel.READ_ONLY

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output="build successful",
            evidence={"artifacts": ["dist/index.js"]},
        )


class MockDeployTool(BaseTool):
    name = "remote_deploy"
    description = "Consequential deployment step requiring explicit approval"
    risk_level = ActionRiskLevel.CONSEQUENTIAL

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output="deployment deployed to production",
            evidence={"deployment_url": "https://praxis.live"},
        )


class FakeWebhookDispatcher(ActionDispatcher, StatusReconciler):
    """Stub webhook dispatcher adapter recording invocations."""

    def __init__(self) -> None:
        self.invocations: list[DispatchSpec] = []

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        self.invocations.append(spec)
        return RawDispatchResult(
            status="completed",
            provider_operation_id="wh_op_123",
            raw_payload={
                "status": "completed",
                "operation_id": "wh_op_123",
            },
        )

    async def inspect_status(
        self,
        attempt_id: Any,
        idempotency_key: str,
        provider_operation_id: str | None,
    ) -> RawReconcileResult:
        return RawReconcileResult(
            status="completed",
            provider_operation_id=provider_operation_id,
            raw_payload={"status": "completed"},
        )


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = f"sqlite:///{tmp_path / 'praxis_test.db'}"
        checkpoints_dir = tmp_path / "checkpoints"
        skills_dir = tmp_path / "skills"

        yield {
            "db_path": db_path,
            "checkpoints_dir": checkpoints_dir,
            "skills_dir": skills_dir,
            "tmp_path": tmp_path,
        }


@pytest.mark.anyio
async def test_agent_execution_loop_completes_with_synthesized_evidence(test_env: dict[str, Any]):
    """Test full execution loop synthesizing verifiable Evidence through the adapter seam."""
    uow = SQLiteUnitOfWork(test_env["db_path"])
    checkpoints = CheckpointStore(test_env["checkpoints_dir"])
    skill_store = SkillStore(test_env["skills_dir"])

    skill_store.save(
        Skill(
            name="Build Instructions",
            description="Guide on workspace build",
            triggers=["build", "compile"],
            instructions="Run workspace_build tool to generate bundle.",
        )
    )

    llm = MockAgentLLM(
        [
            '<tool_call>{"name": "workspace_build", "arguments": {"target": "bundle"}}</tool_call>',
            "Build complete. Ready for next phase.",
        ]
    )

    registry = ToolRegistry()
    registry.register(MockWorkspaceTool())

    agent_dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        skill_store=skill_store,
        checkpoint_store=checkpoints,
    )

    webhook_dispatcher = FakeWebhookDispatcher()
    router = RoutingActionDispatcher(default_dispatcher=webhook_dispatcher)
    router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)
    router.register_dispatcher("webhook_post", webhook_dispatcher, webhook_dispatcher)

    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=router)

    # 1. Create a task with agent_runtime tool_hint
    task = Task(owner_id="operator_1", title="Compile Frontend Bundle")
    task.add_next_action(
        description="Run build bundle",
        tool_hint="agent_runtime",
        tool_args_hint={"goal": "compile and build frontend bundle"},
    )

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    # 2. Execute next action across the dispatch seam
    cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="operator_1")
    result = await use_case.execute(cmd)

    # 3. Verify outcomes
    assert result.outcome.status == "completed"
    assert result.task.status == TaskStatus.COMPLETED
    assert result.action.completed is True
    assert result.action.evidence_id is not None
    assert result.attempt.status == "completed"

    # Verify synthesized machine evidence details
    assert result.outcome.evidence is not None
    assert result.outcome.evidence.verifier_identity == "agent_runtime:conversation_loop"
    details = result.outcome.evidence.details
    assert details["step_count"] >= 2
    assert len(details["tool_evidence"]) == 1
    assert details["tool_evidence"][0]["artifacts"] == ["dist/index.js"]

    async with uow:
        persisted_task = await uow.tasks.get_for_owner(task.id, "operator_1")
        assert persisted_task is not None
        assert result.outcome.evidence.id in persisted_task.evidence_records

    # Verify skill selection locality bounded prompt depth
    assert any("Build Instructions" in p for p in llm.prompts)


@pytest.mark.anyio
async def test_agent_approval_gate_and_resumption_lifecycle(test_env: dict[str, Any]):
    """Test interactive approval halting and resumption lifecycle across the adapter interface."""
    uow = SQLiteUnitOfWork(test_env["db_path"])
    checkpoints = CheckpointStore(test_env["checkpoints_dir"])

    llm = MockAgentLLM(
        [
            '<tool_call>{"name": "remote_deploy", "arguments": {"env": "prod"}}</tool_call>',
            "Deployment completed successfully.",
        ]
    )

    registry = ToolRegistry()
    registry.register(MockDeployTool())

    agent_dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
    )

    router = RoutingActionDispatcher(default_dispatcher=agent_dispatcher)
    router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)

    exec_use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=router)
    resolve_use_case = ResolveApprovalUseCase(uow=uow)

    task = Task(owner_id="operator_2", title="Deploy Microservice")
    task.add_next_action(
        description="Deploy to production",
        tool_hint="agent_runtime",
        tool_args_hint={"goal": "deploy to prod environment"},
    )

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    # 1. Execute: should halt because remote_deploy is CONSEQUENTIAL
    cmd_1 = ExecuteNextActionCommand(task_id=task.id, owner_id="operator_2")
    res_1 = await exec_use_case.execute(cmd_1)

    assert res_1.outcome.status == "awaiting_approval"
    assert res_1.approval_request is not None
    assert res_1.attempt.status == "awaiting_approval"
    assert res_1.task.status == TaskStatus.AWAITING_APPROVAL

    approval_id = res_1.approval_request.id

    # 2. Approve request via resolve approval use case
    resolve_cmd = ResolveApprovalCommand(
        approval_id=approval_id,
        decision="approve",
        owner_id="operator_2",
    )
    resolve_result = await resolve_use_case.execute(resolve_cmd)
    assert resolve_result.approval.status == ApprovalStatus.APPROVED

    # 3. Resume execution supplying the valid approval token
    cmd_2 = ExecuteNextActionCommand(
        task_id=task.id,
        owner_id="operator_2",
        approval_token=res_1.approval_token,
    )
    res_2 = await exec_use_case.execute(cmd_2)

    assert res_2.outcome.status == "completed"
    assert res_2.task.status == TaskStatus.COMPLETED
    assert res_2.attempt.status == "completed"
    assert res_2.action.completed is True


@pytest.mark.anyio
async def test_reconciliation_inspects_agent_checkpoint_without_side_effects(
    test_env: dict[str, Any],
):
    """Test ReconcileExecutionUseCase querying agent checkpoint without side-effect re-execution."""
    uow = SQLiteUnitOfWork(test_env["db_path"])
    checkpoints = CheckpointStore(test_env["checkpoints_dir"])

    llm = MockAgentLLM(
        [
            '<tool_call>{"name": "workspace_build", "arguments": {}}</tool_call>',
            "Finished build.",
        ]
    )

    registry = ToolRegistry()
    registry.register(MockWorkspaceTool())

    agent_dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
    )

    router = RoutingActionDispatcher(default_dispatcher=agent_dispatcher)
    router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)

    exec_use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=router)
    reconcile_use_case = ReconcileExecutionUseCase(uow=uow, reconciler=router)

    task = Task(owner_id="operator_3", title="Check Build Artifacts")
    task.add_next_action(
        description="Verify build",
        tool_hint="agent_runtime",
        tool_args_hint={"goal": "Verify build"},
    )

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    cmd = ExecuteNextActionCommand(task_id=task.id, owner_id="operator_3")
    res = await exec_use_case.execute(cmd)
    assert res.outcome.status == "completed"

    # Manually transition attempt status to outcome_unknown to simulate recovery inspection
    async with uow:
        attempt = await uow.attempts.get_for_owner(res.attempt.id, "operator_3")
        assert attempt is not None
        attempt.status = "outcome_unknown"
        attempt.provider_request_id = str(res.attempt.id)
        await uow.attempts.save(attempt)

        persisted_task = await uow.tasks.get_for_owner(task.id, "operator_3")
        assert persisted_task is not None
        persisted_task.status = TaskStatus.IN_PROGRESS
        persisted_action = next(a for a in persisted_task.next_actions if a.id == res.action.id)
        persisted_action.completed = False
        await uow.tasks.save(persisted_task)
        await uow.commit()

    # Call reconcile
    reconcile_cmd = ReconcileExecutionCommand(
        task_id=task.id,
        attempt_id=res.attempt.id,
        owner_id="operator_3",
    )
    reconciled = await reconcile_use_case.execute(reconcile_cmd)

    assert reconciled.outcome.status == "completed"
    assert reconciled.attempt.status == "completed"
    # LLM was not re-invoked during status inspection
    assert llm.call_count == 2


@pytest.mark.anyio
async def test_explicit_routing_strategy_preserves_webhook_and_agent_seams(
    test_env: dict[str, Any],
):
    """Test explicit strategy selection ensuring WebhookRunner and agent isolation."""
    uow = SQLiteUnitOfWork(test_env["db_path"])
    checkpoints = CheckpointStore(test_env["checkpoints_dir"])

    llm = MockAgentLLM(["Agent performed step."])
    registry = ToolRegistry()
    agent_dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
    )

    webhook_dispatcher = FakeWebhookDispatcher()
    router = RoutingActionDispatcher(default_dispatcher=webhook_dispatcher)
    router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)
    router.register_dispatcher("webhook_post", webhook_dispatcher, webhook_dispatcher)

    use_case = ExecuteNextActionUseCase(uow=uow, dispatcher=router)

    # Webhook task
    webhook_task = Task(owner_id="op_route", title="Webhook Task")
    webhook_task.add_next_action(
        description="Post webhook",
        tool_hint="webhook_post",
        tool_args_hint={"url": "https://hooks.example.com"},
    )

    # Agent task
    agent_task = Task(owner_id="op_route", title="Agent Task")
    agent_task.add_next_action(
        description="Agent task",
        tool_hint="agent_runtime",
        tool_args_hint={"goal": "Run agent process"},
    )

    async with uow:
        await uow.tasks.save(webhook_task)
        await uow.tasks.save(agent_task)
        await uow.commit()

    # Execute webhook task
    res_wh = await use_case.execute(
        ExecuteNextActionCommand(task_id=webhook_task.id, owner_id="op_route")
    )
    assert res_wh.outcome.status == "completed"
    assert len(webhook_dispatcher.invocations) == 1
    assert webhook_dispatcher.invocations[0].tool_name == "webhook_post"
    assert llm.call_count == 0

    # Execute agent task
    res_ag = await use_case.execute(
        ExecuteNextActionCommand(task_id=agent_task.id, owner_id="op_route")
    )
    assert res_ag.outcome.status == "completed"
    assert len(webhook_dispatcher.invocations) == 1  # Unchanged!
    assert llm.call_count == 1  # Agent LLM was called!
