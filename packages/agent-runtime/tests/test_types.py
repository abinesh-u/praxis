"""Tests for runtime types and data containers."""

from praxis_agent_runtime.types import (
    ActionRiskLevel,
    ApprovalRequired,
    ExecutionStatus,
    RunRecord,
    StepRecord,
    ToolResult,
)


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, output="file contents", evidence={"size": 42})
        assert r.success is True
        assert r.evidence["size"] == 42

    def test_failure_result(self):
        r = ToolResult(success=False, error="file not found")
        assert r.success is False
        assert r.error == "file not found"


class TestRunRecord:
    def test_add_step_updates_tokens(self):
        run = RunRecord(goal="test task", max_steps=5)
        assert run.status == ExecutionStatus.PENDING
        assert run.total_tokens_used == 0

        step = StepRecord(step_index=0, step_type="llm_response", token_count=150)
        run.add_step(step)
        assert run.total_tokens_used == 150
        assert len(run.steps) == 1

    def test_add_step_without_tokens(self):
        run = RunRecord(goal="test")
        step = StepRecord(step_index=0, step_type="tool_result")
        run.add_step(step)
        assert run.total_tokens_used == 0


class TestApprovalRequired:
    def test_exception_carries_details(self):
        exc = ApprovalRequired("fs_write_file", {"path": "x"}, ActionRiskLevel.CONSEQUENTIAL)
        assert exc.tool_name == "fs_write_file"
        assert exc.risk_level == ActionRiskLevel.CONSEQUENTIAL
        assert "approval" in str(exc).lower()
