"""TaskExtractor port defining the interface for AI-assisted task extraction."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from praxis_core.entities.common import Priority


class ExtractedTaskData(BaseModel):
    """Structured task information parsed from natural language.

    Tool hints and risk suggestions are strictly proposals and must be verified
    against trusted tool registries before execution.
    """

    title: str
    description: str = ""
    priority: Priority = Priority.ROUTINE
    due_date: datetime | None = None
    scheduled_date: datetime | None = None
    next_action_description: str = ""
    suggested_tool_hint: str | None = None
    suggested_tool_args: dict[str, Any] = Field(default_factory=dict)
    clarification_needed: bool = False
    clarification_prompt: str | None = None


class TaskExtractor(Protocol):
    """Protocol for extracting structured task intent from conversational input."""

    async def extract(
        self,
        text: str,
        reference_time: datetime,
        user_timezone: str = "UTC",
    ) -> ExtractedTaskData:
        """Extract structured task data with explicit timezone and reference time context."""
        ...
