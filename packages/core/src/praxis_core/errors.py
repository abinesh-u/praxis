"""Domain error hierarchy for Praxis Core."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID


class DomainError(Exception):
    """Base class for all domain exceptions in Praxis Core."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidStateTransitionError(DomainError):
    """Raised when an illegal lifecycle transition is attempted on a task."""

    def __init__(self, from_status: str, to_status: str, reason: str = "") -> None:
        self.from_status = from_status
        self.to_status = to_status
        msg = f"Cannot transition task from '{from_status}' to '{to_status}'"
        if reason:
            msg += f": {reason}"
        super().__init__(
            msg,
            {"from_status": from_status, "to_status": to_status, "reason": reason},
        )


class BlockedTaskError(DomainError):
    """Raised when a task cannot start because of unsatisfied blocking dependencies."""

    def __init__(self, task_id: UUID, blocking_task_ids: list[UUID]) -> None:
        self.task_id = task_id
        self.blocking_task_ids = blocking_task_ids
        msg = f"Task {task_id} is blocked by incomplete tasks: {blocking_task_ids}"
        super().__init__(
            msg,
            {
                "task_id": str(task_id),
                "blocking_task_ids": [str(id_) for id_ in blocking_task_ids],
            },
        )


class EvidenceRequiredError(DomainError):
    """Raised when attempting to complete a task without valid verification evidence."""

    def __init__(self, task_id: UUID, reason: str = "Completion requires evidence") -> None:
        self.task_id = task_id
        super().__init__(
            f"Cannot complete task {task_id}: {reason}",
            {"task_id": str(task_id), "reason": reason},
        )


class EvidenceVerificationFailedError(DomainError):
    """Raised when provided evidence fails verification against requirements."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Evidence verification failed: {reason}", {"reason": reason})


class InvalidApprovalError(DomainError):
    """Raised when an approval is invalid or in an unexpected state."""

    def __init__(self, approval_id: UUID, reason: str) -> None:
        self.approval_id = approval_id
        super().__init__(
            f"Approval {approval_id} invalid: {reason}",
            {"approval_id": str(approval_id), "reason": reason},
        )


class ApprovalExpiredError(DomainError):
    """Raised when attempting to decide or consume an expired approval."""

    def __init__(self, approval_id: UUID, expires_at: datetime) -> None:
        self.approval_id = approval_id
        self.expires_at = expires_at
        super().__init__(
            f"Approval {approval_id} expired at {expires_at.isoformat()}",
            {"approval_id": str(approval_id), "expires_at": expires_at.isoformat()},
        )


class ApprovalAlreadyConsumedError(DomainError):
    """Raised when attempting to reuse an approval token that has already been consumed."""

    def __init__(self, approval_id: UUID) -> None:
        self.approval_id = approval_id
        super().__init__(
            f"Approval {approval_id} already consumed (single-use invariant)",
            {"approval_id": str(approval_id)},
        )


class ApprovalActionMismatchError(DomainError):
    """Raised when the presented action parameters do not match approved action fingerprint."""

    def __init__(self, expected_fingerprint: str, actual_fingerprint: str) -> None:
        self.expected_fingerprint = expected_fingerprint
        self.actual_fingerprint = actual_fingerprint
        super().__init__(
            "Action execution parameters do not match approved action fingerprint",
            {
                "expected_fingerprint": expected_fingerprint,
                "actual_fingerprint": actual_fingerprint,
            },
        )


class SelfDependencyError(DomainError):
    """Raised when a task is declared to depend on itself."""

    def __init__(self, task_id: UUID) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} cannot depend on itself", {"task_id": str(task_id)})


class DependencyCycleError(DomainError):
    """Raised when adding a dependency introduces a circular dependency."""

    def __init__(self, cycle_path: list[UUID]) -> None:
        self.cycle_path = cycle_path
        path_str = " -> ".join(str(tid) for tid in cycle_path)
        super().__init__(
            f"Circular dependency detected: {path_str}",
            {"cycle_path": [str(t) for t in cycle_path]},
        )


class ConcurrencyConflictError(DomainError):
    """Raised on optimistic locking conflict when updating an aggregate."""

    def __init__(self, entity_id: UUID, expected_version: int, actual_version: int) -> None:
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        msg = (
            f"Concurrency conflict on {entity_id}: "
            f"expected v{expected_version}, got v{actual_version}"
        )
        super().__init__(
            msg,
            {
                "entity_id": str(entity_id),
                "expected_version": expected_version,
                "actual_version": actual_version,
            },
        )


class EntityNotFoundError(DomainError):
    """Raised when an entity is not found in a repository."""

    def __init__(self, entity_type: str, entity_id: UUID | str) -> None:
        self.entity_type = entity_type
        self.entity_id = str(entity_id)
        super().__init__(
            f"{entity_type} with ID '{entity_id}' not found",
            {"entity_type": entity_type, "entity_id": str(entity_id)},
        )


class AmbiguousIdentifierError(DomainError):
    """Raised when an identifier or prefix matches multiple entities within an owner scope."""

    def __init__(self, message: str) -> None:
        super().__init__(message, {"error_type": "AmbiguousIdentifierError"})


class IdempotencyConflictError(DomainError):
    """Raised when an idempotency key is reused with conflicting input."""

    def __init__(self, key: str, reason: str = "Conflicting payload for idempotency key") -> None:
        self.key = key
        self.reason = reason
        super().__init__(
            f"Idempotency conflict for key '{key}': {reason}",
            {"key": key, "reason": reason},
        )


class StaleInferenceError(DomainError):
    """Raised when inference results arrive for a stale commitment revision."""

    def __init__(self, commitment_id: UUID, expected_revision: int, actual_revision: int) -> None:
        self.commitment_id = commitment_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"Stale inference on commitment {commitment_id}: "
            f"expected revision {expected_revision}, got {actual_revision}",
            {
                "commitment_id": str(commitment_id),
                "expected_revision": expected_revision,
                "actual_revision": actual_revision,
            },
        )


class InvalidClarificationTargetError(DomainError):
    """Raised when clarification is attempted on an ineligible commitment."""

    def __init__(self, commitment_id: UUID, reason: str) -> None:
        self.commitment_id = commitment_id
        self.reason = reason
        super().__init__(
            f"Cannot clarify commitment {commitment_id}: {reason}",
            {"commitment_id": str(commitment_id), "reason": reason},
        )


class IntakeValidationError(DomainError):
    """Raised when extracted or provided intake proposal violates domain constraints."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        self.reason = reason
        payload = {"reason": reason}
        if details:
            payload.update(details)
        super().__init__(f"Intake validation failed: {reason}", payload)
