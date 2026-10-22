"""Shared types, enums, and data containers for the agent runtime."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActionRiskLevel(StrEnum):
    """How dangerous is this tool's side effect?"""

    READ_ONLY = "read_only"  # Just reads data, no changes
    LOW_RISK = "low_risk"  # Creates/modifies local drafts, easily reversible
    CONSEQUENTIAL = "consequential"  # Writes files, sends data — needs approval
    DESTRUCTIVE = "destructive"  # Deletes data, irreversible — always needs approval


class ExecutionStatus(StrEnum):
    """Lifecycle state of an agent execution run."""

    PENDING = "pending"  # Created but not started
    RUNNING = "running"  # Actively executing steps
    AWAITING_APPROVAL = "awaiting_approval"  # Paused — waiting for user to approve a tool
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Stopped due to error
    BUDGET_EXHAUSTED = "budget_exhausted"  # Hit step or token limit
    CANCELLED = "cancelled"  # User cancelled


class ToolResult(BaseModel):
    """The outcome of executing a single tool."""

    success: bool
    output: Any = None  # The tool's return value
    evidence: dict[str, Any] | None = None  # Observable proof (file hash, returncode, size)
    error: str | None = None  # Error message if success=False
    duration_ms: int | None = None  # Execution duration in milliseconds


class ParsedToolCall(BaseModel):
    """A tool invocation extracted from model output."""

    name: str  # Tool name, e.g. "fs_read_file"
    arguments: dict[str, Any] = Field(default_factory=dict)  # Tool arguments


class StepRecord(BaseModel):
    """A single step in an execution run (either an LLM response or a tool result)."""

    step_index: int
    step_type: str  # "llm_response", "tool_call", "tool_result", "error"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: ToolResult | None = None
    token_count: int | None = None


class RunRecord(BaseModel):
    """Complete record of an agent execution run."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ExecutionStatus = ExecutionStatus.PENDING
    goal: str = ""
    steps: list[StepRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_tokens_used: int = 0
    max_steps: int = 10
    error: str | None = None

    def add_step(self, step: StepRecord) -> None:
        """Append a step and update metadata."""
        self.steps.append(step)
        if step.token_count:
            self.total_tokens_used += step.token_count
        self.updated_at = datetime.now(UTC)


class ApprovalRequiredError(Exception):
    """Raised when a tool needs user approval before execution."""

    def __init__(self, tool_name: str, arguments: dict[str, Any], risk_level: ActionRiskLevel):
        self.tool_name = tool_name
        self.arguments = arguments
        self.risk_level = risk_level
        super().__init__(f"Tool '{tool_name}' requires approval (risk: {risk_level.value})")


# Alias for backward-compatibility with earlier drafts
ApprovalRequired = ApprovalRequiredError
