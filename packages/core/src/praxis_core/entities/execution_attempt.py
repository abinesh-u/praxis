"""ExecutionAttempt entity for durable tracking of agent tool execution attempts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionAttempt(BaseModel):
    """Durable record of an agent execution attempt.

    Enforces crash recoverability: persisted before invoking external tools,
    reconciled with evidence after completion.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    owner_id: str
    task_id: UUID
    action_id: UUID
    idempotency_key: str
    status: str = "pending"  # pending, running, completed, awaiting_approval, failed
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    evidence_id: UUID | None = None
    error: str | None = None
    approval_id: UUID | None = None

    def mark_running(self, when: datetime | None = None) -> None:
        """Mark attempt as actively executing."""
        self.status = "running"
        self.started_at = when or datetime.now(UTC)

    def mark_completed(self, evidence_id: UUID, when: datetime | None = None) -> None:
        """Mark attempt as verified and completed."""
        self.status = "completed"
        self.completed_at = when or datetime.now(UTC)
        self.evidence_id = evidence_id

    def mark_awaiting_approval(self, approval_id: UUID, when: datetime | None = None) -> None:
        """Mark attempt as paused waiting for human authorization."""
        self.status = "awaiting_approval"
        self.approval_id = approval_id

    def mark_failed(self, error: str, when: datetime | None = None) -> None:
        """Mark attempt as failed."""
        self.status = "failed"
        self.completed_at = when or datetime.now(UTC)
        self.error = error
