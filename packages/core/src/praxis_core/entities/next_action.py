"""NextAction entity representing the single concrete physical step to execute."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from praxis_core.entities.common import ActionRiskLevel


class NextAction(BaseModel):
    """The smallest, friction-free physical step toward completing a task.

    Designed specifically to reduce task initiation paralysis by making the
    immediate action unambiguous.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    task_id: UUID
    owner_id: str
    description: str
    tool_hint: str | None = None
    tool_args_hint: dict[str, Any] | None = None
    risk_level: ActionRiskLevel = ActionRiskLevel.READ_ONLY
    completed: bool = False
    completed_at: datetime | None = None
    evidence_id: UUID | None = None
    sort_order: int = 0
    execution_attempts: int = 0
    last_attempt_at: datetime | None = None

    def mark_completed(self, evidence_id: UUID | None = None, when: datetime | None = None) -> None:
        """Mark this concrete action as verified and completed."""
        self.completed = True
        self.completed_at = when or datetime.now(UTC)
        if evidence_id:
            self.evidence_id = evidence_id

    def record_attempt(self, when: datetime | None = None) -> None:
        """Increment execution attempts without completing."""
        self.execution_attempts += 1
        self.last_attempt_at = when or datetime.now(UTC)
