"""Tool Registry — catalogs tools, validates calls, and enforces approval gates."""

from __future__ import annotations

import json
from typing import Any

from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.types import ApprovalRequired, ToolResult


class ToolNotFoundError(Exception):
    """Raised when a tool name is not in the registry."""


class ToolRegistry:
    """Manages registered tools, argument validation, and approval enforcement."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._approved_calls: set[str] = set()

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """Look up a tool by name."""
        if name not in self._tools:
            raise ToolNotFoundError(f"Unknown tool: '{name}'")
        return self._tools[name]

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def grant_approval(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Pre-approve a specific tool call."""
        key = self._approval_key(tool_name, arguments)
        self._approved_calls.add(key)

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Validate, check approval, and execute a tool."""
        tool = self.get(tool_name)

        if tool.requires_approval:
            key = self._approval_key(tool_name, arguments)
            if key not in self._approved_calls:
                raise ApprovalRequired(tool_name, arguments, tool.risk_level)
            self._approved_calls.discard(key)

        return tool.run(arguments)

    @staticmethod
    def _approval_key(tool_name: str, arguments: dict[str, Any]) -> str:
        """Generate a deterministic key for an approval grant."""
        args_sorted = json.dumps(arguments, sort_keys=True, default=str)
        return f"{tool_name}:{args_sorted}"
