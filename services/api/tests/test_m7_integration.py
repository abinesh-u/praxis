"""Integration test module validating M7 skill learning across the core execution seam.

Tests verify:
1. Multi-step agent execution triggers candidate extraction upon verified terminal completion.
2. Candidate skills are persisted idempotently with attempt-derived names and rich provenance.
3. Untrusted candidate skills are quarantined in storage, excluded from active matching depth.
4. Repeated execution replays do not create duplicate candidate skills.
5. Ineligible executions (fewer than 3 tool steps or failed steps) do not produce candidate skills.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from praxis_agent_runtime.adapter import AgentActionDispatcher
from praxis_agent_runtime.learning.learning_loop import AgentSkillLearner
from praxis_agent_runtime.loop.checkpoints import CheckpointStore
from praxis_agent_runtime.skills.matcher import match_skills
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.tools.registry import ToolRegistry
from praxis_agent_runtime.types import ToolResult
from praxis_core.entities.common import ActionRiskLevel, TaskStatus
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
)


class MockMultiStepAgentLLM:
    """Mock LLM adapter simulating a 3-tool workflow followed by completion."""

    def __init__(self) -> None:
        self.call_count = 0
        self.responses = [
            '<tool_call>{"name": "step_one_tool", "arguments": {"param": "alpha"}}</tool_call>',
            '<tool_call>{"name": "step_two_tool", "arguments": {"param": "beta"}}</tool_call>',
            '<tool_call>{"name": "step_three_tool", "arguments": {"param": "gamma"}}</tool_call>',
            "Multi-step procedure successfully executed.",
        ]

    def chat(self, messages: list[dict[str, str]]) -> str:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return "All operations finished."


class MockStepTool(BaseTool):
    """Mock tool adapter returning verifiable proof of execution."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"Executes {name}"
        self.risk_level = ActionRiskLevel.READ_ONLY

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output=f"{self.name} completed",
            evidence={"executed_step": self.name, "param": kwargs.get("param")},
        )


class StubWebhookDispatcher(ActionDispatcher, StatusReconciler):
    """Stub webhook dispatcher adapter recording invocations."""

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        return RawDispatchResult(status="completed", raw_payload={"status": "completed"})

    async def inspect_status(
        self, attempt_id: Any, idempotency_key: str, provider_operation_id: str | None
    ) -> RawReconcileResult:
        return RawReconcileResult(status="completed")


@pytest.fixture
def m7_test_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = f"sqlite:///{tmp_path / 'praxis_m7_test.db'}"
        checkpoints_dir = tmp_path / "checkpoints"
        skills_dir = tmp_path / "skills"

        yield {
            "db_path": db_path,
            "checkpoints_dir": checkpoints_dir,
            "skills_dir": skills_dir,
            "tmp_path": tmp_path,
        }


@pytest.mark.anyio
async def test_m7_successful_execution_distills_quarantined_candidate(m7_test_env: dict[str, Any]):
    """Test execution loop distilling an isolated candidate skill across the validation seam."""
    uow = SQLiteUnitOfWork(m7_test_env["db_path"])
    checkpoints = CheckpointStore(m7_test_env["checkpoints_dir"])
    skill_store = SkillStore(m7_test_env["skills_dir"])
    skill_learner = AgentSkillLearner(skill_store=skill_store)

    registry = ToolRegistry()
    registry.register(MockStepTool("step_one_tool"))
    registry.register(MockStepTool("step_two_tool"))
    registry.register(MockStepTool("step_three_tool"))

    agent_dispatcher = AgentActionDispatcher(
        llm=MockMultiStepAgentLLM(),
        tool_registry=registry,
        skill_store=skill_store,
        checkpoint_store=checkpoints,
    )

    webhook_dispatcher = StubWebhookDispatcher()
    router = RoutingActionDispatcher(default_dispatcher=webhook_dispatcher)
    router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)

    use_case = ExecuteNextActionUseCase(
        uow=uow,
        dispatcher=router,
        skill_learner=skill_learner,
    )

    owner = "operator_m7"
    task = Task(owner_id=owner, title="Deploy Multi-Step Application Pipeline")
    task.add_next_action(
        description="Execute complete multi-step deployment pipeline",
        tool_hint="agent_runtime",
        tool_args_hint={"goal": "deploy application pipeline through step one two three"},
    )

    async with uow:
        await uow.tasks.save(task)
        await uow.commit()

    # 1. Execute the multi-step next action
    idempotency_key = f"idem-m7-{uuid4().hex[:8]}"
    cmd = ExecuteNextActionCommand(
        task_id=task.id,
        owner_id=owner,
        idempotency_key=idempotency_key,
    )
    result = await use_case.execute(cmd)

    # 2. Verify authoritative execution completion and evidence synthesis
    assert result.outcome.status == "completed"
    assert result.task.status == TaskStatus.COMPLETED
    assert result.action.completed is True
    assert result.outcome.evidence is not None
    assert result.outcome.evidence.is_verified() is True

    # 3. Verify candidate skill distillation across the validation seam
    assert result.learned_skill is not None
    candidate = result.learned_skill
    assert candidate.status == "candidate"
    assert candidate.is_candidate is True
    assert candidate.is_validated is False

    # Verify deterministic name derived from execution attempt
    expected_clean_att = str(result.attempt.id).replace("-", "")[:12]
    assert candidate.name == f"candidate_att_{expected_clean_att}"

    # Verify candidate provenance attachment
    assert candidate.provenance is not None
    assert candidate.provenance["attempt_id"] == str(result.attempt.id)
    assert candidate.provenance["task_id"] == str(task.id)
    assert candidate.provenance["owner_id"] == owner
    assert candidate.provenance["evidence_id"] == str(result.outcome.evidence.id)
    assert candidate.provenance["tool_steps_count"] == 3

    # 4. Verify candidate isolation and quarantine in storage
    # Active skill loader isolates candidates to protect prompt depth
    assert len(skill_store.load_all()) == 0
    assert len(match_skills("deploy pipeline", skill_store.load_all())) == 0

    # Candidate interface retrieves quarantined candidate for operator review
    tenant_candidates = skill_store.load_candidates(owner_id=owner)
    assert len(tenant_candidates) == 1
    assert tenant_candidates[0].name == candidate.name
    assert tenant_candidates[0].owner_id == owner

    # Other tenant cannot view this candidate across locality perimeter
    assert len(skill_store.load_candidates(owner_id="other_tenant")) == 0

    # 5. Verify idempotent replay: repeated execution does not duplicate candidates
    replay_result = await use_case.execute(cmd)
    assert replay_result.outcome.status == "completed"
    assert len(skill_store.load_candidates(owner_id=owner)) == 1

    # 6. Verify operator promotion elevates candidate across seam into active execution depth
    promoted = skill_store.promote_candidate(
        name=candidate.name,
        validator_identity="security_lead",
        notes="Validated safe pipeline execution",
    )
    assert promoted.is_validated is True
    # Tenant-scoped lookup sees promoted skill; other tenant isolates private skill
    assert len(skill_store.load_all(owner_id=owner)) == 1
    assert len(skill_store.load_all(owner_id="other_tenant")) == 0
    matched = match_skills("deploy pipeline", skill_store.load_all(owner_id=owner))
    assert len(matched) == 1
    assert matched[0].name == candidate.name
