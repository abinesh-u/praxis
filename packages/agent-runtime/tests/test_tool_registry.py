"""Tests for the tool registry and approval gates."""

import pytest
from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.tools.registry import ToolNotFoundError, ToolRegistry
from praxis_agent_runtime.types import ActionRiskLevel, ApprovalRequired, ToolResult


class DummyReadTool(BaseTool):
    name = "dummy_read"
    description = "A safe read tool for testing"
    risk_level = ActionRiskLevel.READ_ONLY

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="read result")


class DummyWriteTool(BaseTool):
    name = "dummy_write"
    description = "A risky write tool for testing"
    risk_level = ActionRiskLevel.CONSEQUENTIAL

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="wrote something")


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register(DummyReadTool())
        tool = reg.get("dummy_read")
        assert tool.name == "dummy_read"

    def test_get_unknown_raises(self):
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get("nonexistent")

    def test_duplicate_register_raises(self):
        reg = ToolRegistry()
        reg.register(DummyReadTool())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(DummyReadTool())

    def test_execute_safe_tool(self):
        reg = ToolRegistry()
        reg.register(DummyReadTool())
        result = reg.execute("dummy_read", {})
        assert result.success is True

    def test_execute_risky_tool_without_approval_raises(self):
        reg = ToolRegistry()
        reg.register(DummyWriteTool())
        with pytest.raises(ApprovalRequired):
            reg.execute("dummy_write", {})

    def test_execute_risky_tool_with_approval_succeeds(self):
        reg = ToolRegistry()
        reg.register(DummyWriteTool())
        reg.grant_approval("dummy_write", {})
        result = reg.execute("dummy_write", {})
        assert result.success is True

    def test_approval_is_single_use(self):
        reg = ToolRegistry()
        reg.register(DummyWriteTool())
        reg.grant_approval("dummy_write", {})
        reg.execute("dummy_write", {})
        with pytest.raises(ApprovalRequired):
            reg.execute("dummy_write", {})

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(DummyReadTool())
        reg.register(DummyWriteTool())
        assert len(reg.list_tools()) == 2
