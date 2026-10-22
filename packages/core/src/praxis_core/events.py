"""Domain events for Praxis Core.

Domain events capture meaningful state transitions and business occurrences
within domain aggregates without directly coupling to persistence or messaging.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """Base class for all domain events."""

    event_id: UUID = Field(default_factory=uuid.uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    owner_id: str
    aggregate_id: UUID
    event_type: str

    model_config = {"frozen": True}


class TaskCreatedEvent(DomainEvent):
    """Emitted when a new task is created."""

    event_type: str = "task.created"
    title: str
    priority: str


class TaskStatusChangedEvent(DomainEvent):
    """Emitted when a task transitions from one lifecycle status to another."""

    event_type: str = "task.status_changed"
    from_status: str
    to_status: str
    reason: str | None = None


class TaskDeferredEvent(DomainEvent):
    """Emitted when a task is rescheduled/deferred without guilt."""

    event_type: str = "task.deferred"
    deferred_until: datetime
    deferral_count: int
    reason: str | None = None


class TaskCompletedEvent(DomainEvent):
    """Emitted when a task is completed with verified evidence."""

    event_type: str = "task.completed"
    evidence_id: UUID
    verifier_identity: str
    verification_status: str


class TaskFailedEvent(DomainEvent):
    """Emitted when a task encounters an unrecoverable or paused failure."""

    event_type: str = "task.failed"
    failure_reason: str
    recovery_suggestion: str | None = None


class ApprovalRequestedEvent(DomainEvent):
    """Emitted when a consequential action pauses for user confirmation."""

    event_type: str = "approval.requested"
    approval_id: UUID
    tool_name: str
    risk_level: str
    action_fingerprint: str


class ApprovalDecidedEvent(DomainEvent):
    """Emitted when an approval request is approved or rejected."""

    event_type: str = "approval.decided"
    approval_id: UUID
    decision: str  # "approved" or "rejected"
    decided_by: str
    reason: str | None = None
