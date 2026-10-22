"""AgentRunner port defining the execution boundary between core and agent runtime."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.approval import ActionSpecification
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task


class AgentRunOutcome(BaseModel):
    """Normalized outcome returned from executing an agent action."""

    status: str  # "completed", "awaiting_approval", "failed"
    evidence: Evidence | None = None
    action_spec: ActionSpecification | None = None
    action_fingerprint: str | None = None
    approval_justification: str | None = None
    output: Any = None
    error: str | None = None


class AgentRunner(Protocol):
    """Protocol for executing a NextAction through a bounded agent runtime."""

    async def execute_action(
        self,
        attempt_id: UUID,
        task: Task,
        action: NextAction,
        owner_id: str,
        workspace_root: str | None = None,
    ) -> AgentRunOutcome:
        """Execute a single next action through the bounded agent loop."""
        ...
