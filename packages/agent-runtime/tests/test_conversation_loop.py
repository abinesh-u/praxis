"""Tests for the fast execution loop using a mock LLM provider."""

import pytest
from praxis_agent_runtime.loop.checkpoints import CheckpointStore
from praxis_agent_runtime.loop.conversation_loop import ConversationLoop, LoopConfig
from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.tools.registry import ToolRegistry
from praxis_agent_runtime.types import (
    ActionRiskLevel,
    ApprovalRequired,
    ExecutionStatus,
    ToolResult,
)


class MockLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    def chat(self, messages: list[dict[str, str]]) -> str:
        if self._call_count >= len(self._responses):
            return "I have completed the task."
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


class EchoTool(BaseTool):
    name = "echo"
    description = "Echoes input back"
    risk_level = ActionRiskLevel.READ_ONLY

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"echo: {kwargs}")


class RiskyTool(BaseTool):
    name = "risky_action"
    description = "Does something consequential"
    risk_level = ActionRiskLevel.CONSEQUENTIAL

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="action performed")


class TestConversationLoop:
    def _make_loop(self, responses, tools=None, max_steps=10, tmp_path=None):
        registry = ToolRegistry()
        for t in tools or [EchoTool()]:
            registry.register(t)
        store = CheckpointStore(str(tmp_path or "/tmp/praxis-test-checkpoints"))
        return ConversationLoop(
            llm=MockLLM(responses),
            registry=registry,
            checkpoint_store=store,
            config=LoopConfig(max_steps=max_steps),
        )

    def test_simple_completion_no_tools(self, tmp_path):
        loop = self._make_loop(
            responses=["Here is your answer. No tools needed."],
            tmp_path=tmp_path,
        )
        run = loop.execute("What is 2+2?")
        assert run.status == ExecutionStatus.COMPLETED
        assert len(run.steps) >= 1

    def test_tool_call_and_completion(self, tmp_path):
        loop = self._make_loop(
            responses=[
                '<tool_call>{"name": "echo", "arguments": {"msg": "hi"}}</tool_call>',
                "Done! The echo result was received.",
            ],
            tmp_path=tmp_path,
        )
        run = loop.execute("Echo something")
        assert run.status == ExecutionStatus.COMPLETED
        tool_results = [s for s in run.steps if s.step_type == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0].tool_result is not None
        assert tool_results[0].tool_result.success is True

    def test_budget_exhaustion(self, tmp_path):
        loop = self._make_loop(
            responses=[
                '<tool_call>{"name": "echo", "arguments": {}}</tool_call>',
            ]
            * 20,
            max_steps=3,
            tmp_path=tmp_path,
        )
        run = loop.execute("Loop forever")
        assert run.status == ExecutionStatus.BUDGET_EXHAUSTED

    def test_approval_required_pauses_loop(self, tmp_path):
        loop = self._make_loop(
            responses=[
                '<tool_call>{"name": "risky_action", "arguments": {}}</tool_call>',
            ],
            tools=[RiskyTool()],
            tmp_path=tmp_path,
        )
        with pytest.raises(ApprovalRequired) as exc_info:
            loop.execute("Do something risky")
        assert exc_info.value.tool_name == "risky_action"

    def test_checkpoint_created(self, tmp_path):
        loop = self._make_loop(
            responses=["Simple answer."],
            tmp_path=tmp_path,
        )
        run = loop.execute("Test checkpoint")
        store = CheckpointStore(str(tmp_path))
        loaded = store.load(run.run_id)
        assert loaded is not None
        assert loaded.status == ExecutionStatus.COMPLETED

    def test_llm_failure_handled(self, tmp_path):
        class FailingLLM:
            def chat(self, messages):
                raise ConnectionError("API down")

        registry = ToolRegistry()
        registry.register(EchoTool())
        store = CheckpointStore(str(tmp_path))
        loop = ConversationLoop(
            llm=FailingLLM(),
            registry=registry,
            checkpoint_store=store,
        )
        run = loop.execute("Try something")
        assert run.status == ExecutionStatus.FAILED
        assert run.error is not None
        assert "API down" in run.error
