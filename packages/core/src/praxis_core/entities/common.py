"""Common enums, value objects, and utility functions for domain entities."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    """Lifecycle state of a task."""

    PLANNED = "planned"  # Created, ready for initiation or scheduled date
    IN_PROGRESS = "in_progress"  # Work has actively started
    AWAITING_APPROVAL = "awaiting_approval"  # Paused for human confirmation of action
    COMPLETED = "completed"  # Successfully executed and verified with evidence
    DEFERRED = "deferred"  # Rescheduled intentionally without guilt or shame
    FAILED = "failed"  # Stopped due to execution failure, requires recovery
    CANCELLED = "cancelled"  # Deliberately abandoned by user


class Priority(StrEnum):
    """Task urgency/importance level."""

    ROUTINE = "routine"  # Standard low-friction administrative or everyday task
    IMPORTANT = "important"  # Meaningful commitment with priority focus
    URGENT = "urgent"  # Immediate attention required / near deadline


class SourceChannel(StrEnum):
    """Origin through which a commitment or task was captured."""

    CLI = "cli"
    WEB = "web"
    TELEGRAM = "telegram"
    API = "api"
    SYSTEM = "system"


class DependencyType(StrEnum):
    """Semantics of a task-to-task dependency."""

    BLOCKS = "blocks"  # Hard blocker: Dependent cannot start until prerequisite is COMPLETED
    RELATION = "relation"  # Informational or contextual link; does not block initiation


class ApprovalStatus(StrEnum):
    """State of an approval request."""

    PENDING = "pending"  # Awaiting human decision
    APPROVED = "approved"  # Explicitly granted; token valid for single use
    REJECTED = "rejected"  # Explicitly denied by user
    EXPIRED = "expired"  # Timed out before decision
    CONSUMED = "consumed"  # Single-use token has been executed


class ActionRiskLevel(StrEnum):
    """Risk tier for proposed tool actions."""

    READ_ONLY = "read_only"  # Safe read operations, no side effects
    LOW_RISK = "low_risk"  # Readily reversible local modifications
    CONSEQUENTIAL = "consequential"  # Modifies persistent data, requires approval
    DESTRUCTIVE = "destructive"  # Deletions or irreversible ops; always requires approval


class EvidenceSource(StrEnum):
    """Origin of verification evidence."""

    USER = "user"  # Explicit human observation or confirmation
    TOOL = "tool"  # Direct output from an authorized execution tool
    INTEGRATION = "integration"  # Webhook or API response from external system
    SYSTEM = "system"  # Automated internal assertion or validation check


class VerificationStatus(StrEnum):
    """Level of verification rigor for an evidence record."""

    UNVERIFIED_ASSERTION = "unverified_assertion"  # Stated but not yet validated
    MACHINE_VERIFIED = "machine_verified"  # Verified (hash, exit code, etc.)
    HUMAN_CONFIRMED = "human_confirmed"  # Legitimate human confirmation


def canonicalize_arguments(args: dict[str, Any] | None) -> str:
    """Return a deterministic JSON string with sorted keys for fingerprinting."""
    if not args:
        return "{}"
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
