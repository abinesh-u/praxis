"""Test module verifying the AgentActionDispatcher adapter across the execution seam.

Tests validate:
1. Skill matching locality and prompt injection depth.
2. Tool allowlists, execution perimeters, and step/tool quotas.
3. Interactive approval gates and checkpoint resumption.
4. Idempotency guarantees avoiding duplicate side effects.
5. Status reconciler inspection without side-effect re-execution.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from praxis_agent_runtime.adapter import AgentActionDispatcher
from praxis_agent_runtime.loop.checkpoints import CheckpointStore
from praxis_agent_runtime.loop.conversation_loop import LoopConfig
from praxis_agent_runtime.skills.models import Skill
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.tools.registry import ToolRegistry
from praxis_agent_runtime.types import (
    ActionRiskLevel,
    ExecutionStatus,
    ToolResult,
)
from praxis_core.ports.action_dispatcher import DispatchSpec


class MockLLM:
    """Mock LLM provider adapter recording messages and returning configured responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.received_messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.received_messages.append(list(messages))
        if self.call_count >= len(self.responses):
            return "Task completed with no further actions required."
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


class EchoTool(BaseTool):
    name = "echo_tool"
    description = "Echoes provided input"
    risk_level = ActionRiskLevel.READ_ONLY

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output=f"echoed: {kwargs}",
            evidence={"echo_output": kwargs},
        )


class ConsequentialTool(BaseTool):
    name = "consequential_write"
    description = "Modifies workspace files requiring explicit approval"
    risk_level = ActionRiskLevel.CONSEQUENTIAL

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output="file modified",
            evidence={"bytes_written": 42},
        )


@pytest.mark.anyio
async def test_agent_dispatcher_executes_simple_completion(tmp_path: Path):
    """Test successful execution through the dispatcher adapter interface."""
    llm = MockLLM(
        ['<tool_call>{"name": "echo_tool", "arguments": {"text": "hello"}}</tool_call>', "Done!"]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
        workspace_root=str(tmp_path),
    )

    attempt_id = uuid.uuid4()
    spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key=f"idem_{attempt_id}",
        tool_name="agent_runtime",
        canonical_args={"goal": "Say hello using echo_tool"},
        destination_context={"workspace_root": str(tmp_path)},
    )

    result = await dispatcher.dispatch(spec)

    assert result.status == "completed"
    assert result.provider_operation_id == str(attempt_id)
    assert isinstance(result.raw_payload, dict)
    assert result.raw_payload["status"] == "completed"
    assert len(result.raw_payload["tool_evidence"]) == 1
    assert result.raw_payload["tool_evidence"][0]["echo_output"] == {"text": "hello"}


@pytest.mark.anyio
async def test_skill_selection_locality_and_prompt_depth(tmp_path: Path):
    """Test that skills from SkillStore are selected by locality and bound prompt depth."""
    skills_dir = tmp_path / "skills"
    store = SkillStore(skills_dir)
    store.save(
        Skill(
            name="Deploy Webhook",
            description="Instructions for webhook deployment",
            triggers=["deploy", "webhook"],
            instructions="Step 1: Check credentials. Step 2: Invoke webhook endpoint.",
        )
    )
    store.save(
        Skill(
            name="Database Backup",
            description="Database backup instructions",
            triggers=["backup", "database"],
            instructions="Run backup dump script.",
        )
    )

    llm = MockLLM(["Understood, following webhook deployment instructions."])
    registry = ToolRegistry()
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        skill_store=store,
        checkpoint_store=checkpoints,
    )

    attempt_id = uuid.uuid4()
    spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key=f"idem_{attempt_id}",
        tool_name="agent_runtime",
        canonical_args={"goal": "Deploy the latest webhook release"},
    )

    result = await dispatcher.dispatch(spec)
    assert result.status == "completed"

    # Verify that the matched skill was injected into the system prompt
    assert len(llm.received_messages) >= 1
    system_prompt = llm.received_messages[0][0]["content"]
    assert "Deploy Webhook" in system_prompt
    assert "Database Backup" not in system_prompt  # Bounded prompt depth!


@pytest.mark.anyio
async def test_tool_allowlist_enforcement(tmp_path: Path):
    """Test that actions not in the allowlist are safely rejected across the perimeter."""
    llm = MockLLM(
        [
            (
                '<tool_call>{"name": "consequential_write", '
                '"arguments": {"target": "test.txt"}}</tool_call>'
            ),
            "Received error, stopping.",
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(ConsequentialTool())
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    config = LoopConfig(allowed_tools={"echo_tool"})  # Only echo_tool is allowlisted

    dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
        config=config,
    )

    attempt_id = uuid.uuid4()
    spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key=f"idem_{attempt_id}",
        tool_name="agent_runtime",
        canonical_args={"goal": "Write to test.txt"},
    )

    result = await dispatcher.dispatch(spec)
    assert result.status == "completed"
    # Verify tool execution was blocked
    steps = result.raw_payload["steps"]
    tool_results = [s for s in steps if s.get("step_type") == "tool_result"]
    assert len(tool_results) == 1
    assert "not in allowlisted tools" in tool_results[0]["content"]


@pytest.mark.anyio
async def test_interactive_approval_halt_and_resumption(tmp_path: Path):
    """Test halting on consequential tool and resuming from checkpoint once approved."""
    llm = MockLLM(
        [
            (
                '<tool_call>{"name": "consequential_write", '
                '"arguments": {"file": "config.json"}}</tool_call>'
            ),
            "File was written successfully.",
        ]
    )
    registry = ToolRegistry()
    registry.register(ConsequentialTool())
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
    )

    attempt_id = uuid.uuid4()
    spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key=f"idem_{attempt_id}",
        tool_name="agent_runtime",
        canonical_args={"goal": "Update config.json"},
    )

    # First run without approval: should halt with awaiting_approval status
    halt_result = await dispatcher.dispatch(spec)
    assert halt_result.status == "awaiting_approval"
    assert halt_result.raw_payload["tool_name"] == "consequential_write"

    # Verify checkpoint on disk is saved as awaiting_approval
    saved_run = checkpoints.load(str(attempt_id))
    assert saved_run is not None
    assert saved_run.status == ExecutionStatus.AWAITING_APPROVAL

    # Second run with approved flag in destination context: resumes checkpoint!
    approved_spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key=f"idem_{attempt_id}",
        tool_name="agent_runtime",
        canonical_args={"goal": "Update config.json"},
        destination_context={"approved": True},
    )

    resumed_result = await dispatcher.dispatch(approved_spec)
    assert resumed_result.status == "completed"
    assert len(resumed_result.raw_payload["tool_evidence"]) == 1
    assert resumed_result.raw_payload["tool_evidence"][0]["bytes_written"] == 42


@pytest.mark.anyio
async def test_idempotent_replay_prevents_duplicate_side_effects(tmp_path: Path):
    """Test that completed runs replay idempotently without re-invoking tools."""
    llm = MockLLM(
        [
            '<tool_call>{"name": "echo_tool", "arguments": {"v": 1}}</tool_call>',
            "Finished echo.",
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
    )

    attempt_id = uuid.uuid4()
    spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key=f"idem_{attempt_id}",
        tool_name="agent_runtime",
        canonical_args={"goal": "Echo value 1"},
    )

    first_result = await dispatcher.dispatch(spec)
    assert first_result.status == "completed"
    assert llm.call_count == 2

    # Second dispatch with identical attempt ID: returns persisted checkpoint
    second_result = await dispatcher.dispatch(spec)
    assert second_result.status == "completed"
    assert second_result.raw_payload == first_result.raw_payload
    # LLM was never called again!
    assert llm.call_count == 2


@pytest.mark.anyio
async def test_status_reconciler_inspection(tmp_path: Path):
    """Test StatusReconciler inspect_status queries checkpoint state without re-executing."""
    llm = MockLLM(['<tool_call>{"name": "echo_tool", "arguments": {}}</tool_call>', "All done!"])
    registry = ToolRegistry()
    registry.register(EchoTool())
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    dispatcher = AgentActionDispatcher(
        llm=llm,
        tool_registry=registry,
        checkpoint_store=checkpoints,
    )

    attempt_id = uuid.uuid4()
    # Query unknown attempt
    reconcile_unknown = await dispatcher.inspect_status(
        attempt_id=attempt_id,
        idempotency_key="key_1",
        provider_operation_id=None,
    )
    assert reconcile_unknown.status == "outcome_unknown"

    # Dispatch to complete
    spec = DispatchSpec(
        attempt_id=attempt_id,
        idempotency_key="key_1",
        tool_name="agent_runtime",
        canonical_args={"goal": "Echo test"},
    )
    await dispatcher.dispatch(spec)

    # Reconcile completed attempt
    reconcile_completed = await dispatcher.inspect_status(
        attempt_id=attempt_id,
        idempotency_key="key_1",
        provider_operation_id=str(attempt_id),
    )
    assert reconcile_completed.status == "completed"
    assert reconcile_completed.provider_operation_id == str(attempt_id)
