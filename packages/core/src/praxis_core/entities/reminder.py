"""ReminderIntent entity representing durable scheduling intent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from praxis_core.entities.common import SourceChannel


class ReminderIntent(BaseModel):
    """Represents a scheduled prompt or reminder intent for a task.

    This captures application-level scheduling intent rather than assuming
    instantaneous delivery.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    task_id: UUID
    owner_id: str
    trigger_at: datetime
    channel: SourceChannel = SourceChannel.WEB
    message: str
    dispatched: bool = False
    dispatched_at: datetime | None = None
    dismissed: bool = False
    dismissed_at: datetime | None = None

    def mark_dispatched(self, when: datetime | None = None) -> None:
        """Record that the scheduler dispatched this reminder."""
        self.dispatched = True
        self.dispatched_at = when or datetime.now(UTC)

    def dismiss(self, when: datetime | None = None) -> None:
        """Mark reminder as dismissed by the user."""
        self.dismissed = True
        self.dismissed_at = when or datetime.now(UTC)
