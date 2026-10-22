"""Task entity representing the central aggregate root for user obligations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr

from praxis_core.entities.common import (
    ActionRiskLevel,
    DependencyType,
    Priority,
    TaskStatus,
)
from praxis_core.entities.dependency import Dependency
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.next_action import NextAction
from praxis_core.errors import (
    BlockedTaskError,
    EvidenceRequiredError,
    InvalidStateTransitionError,
)
from praxis_core.events import (
    DomainEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskDeferredEvent,
    TaskFailedEvent,
    TaskStatusChangedEvent,
)


class Task(BaseModel):
    """Aggregate root for a task/commitment in Praxis.

    Owns the task lifecycle invariants, immediate concrete next actions,
    and prerequisite dependency links.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    owner_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PLANNED
    priority: Priority = Priority.ROUTINE
    version: int = 1  # Optimistic concurrency check
    commitment_id: UUID | None = None
    due_date: datetime | None = None
    scheduled_date: datetime | None = None
    completed_at: datetime | None = None
    deferred_until: datetime | None = None
    deferral_count: int = 0
    failure_reason: str | None = None
    recovery_suggestion: str | None = None
    next_actions: list[NextAction] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    evidence_records: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self._events and self.version == 1:
            self._record_event(
                TaskCreatedEvent(
                    owner_id=self.owner_id,
                    aggregate_id=self.id,
                    title=self.title,
                    priority=self.priority.value,
                )
            )

    def _record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        """Collect and clear all uncommitted domain events."""
        events = list(self._events)
        self._events.clear()
        return events

    def _touch(self, when: datetime | None = None) -> None:
        self.version += 1
        self.updated_at = when or datetime.now(UTC)

    # -------------------------------------------------------------------------
    # State Machine Transitions
    # -------------------------------------------------------------------------

    def start(self, is_blocked: bool = False, when: datetime | None = None) -> None:
        """Transition from PLANNED to IN_PROGRESS.

        Raises:
            InvalidStateTransitionError: If not in PLANNED state.
            BlockedTaskError: If the task has unsatisfied blocking dependencies.
        """
        if self.status != TaskStatus.PLANNED:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.IN_PROGRESS.value)

        if is_blocked:
            blocking_ids = [
                d.depends_on_task_id
                for d in self.dependencies
                if d.dependency_type == DependencyType.BLOCKS
            ]
            raise BlockedTaskError(self.id, blocking_ids)

        old_status = self.status
        self.status = TaskStatus.IN_PROGRESS
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
            )
        )

    def await_approval(self, reason: str = "", when: datetime | None = None) -> None:
        """Pause active execution while waiting for human authorization."""
        if self.status != TaskStatus.IN_PROGRESS:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.AWAITING_APPROVAL.value)

        old_status = self.status
        self.status = TaskStatus.AWAITING_APPROVAL
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason=reason,
            )
        )

    def approval_granted(self, when: datetime | None = None) -> None:
        """Resume execution following granted approval."""
        if self.status != TaskStatus.AWAITING_APPROVAL:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.IN_PROGRESS.value)

        old_status = self.status
        self.status = TaskStatus.IN_PROGRESS
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason="Approval granted",
            )
        )

    def approval_rejected(
        self,
        fatal: bool = False,
        reason: str = "",
        when: datetime | None = None,
    ) -> None:
        """Handle rejected approval.

        If fatal, transitions to FAILED.
        If non-fatal, reverts to PLANNED for alternative planning.
        """
        if self.status != TaskStatus.AWAITING_APPROVAL:
            raise InvalidStateTransitionError(
                self.status.value,
                TaskStatus.FAILED.value if fatal else TaskStatus.PLANNED.value,
            )

        old_status = self.status
        if fatal:
            self.status = TaskStatus.FAILED
            self.failure_reason = f"Approval rejected: {reason}" if reason else "Approval rejected"
            self.recovery_suggestion = "Propose an alternative action or cancel task"
            self._touch(when)
            self._record_event(
                TaskFailedEvent(
                    owner_id=self.owner_id,
                    aggregate_id=self.id,
                    failure_reason=self.failure_reason,
                    recovery_suggestion=self.recovery_suggestion,
                )
            )
        else:
            self.status = TaskStatus.PLANNED
            self._touch(when)

        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason=f"Approval rejected: {reason}",
            )
        )

    def complete(self, evidence: Evidence, when: datetime | None = None) -> None:
        """Complete task with required observable verification evidence.

        Invariant: Completion strictly requires verified evidence.
        Completing a task does NOT automatically synthesize proof for unexecuted next actions.
        """
        if self.status != TaskStatus.IN_PROGRESS:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.COMPLETED.value)

        if evidence.target_task_id != self.id:
            raise EvidenceRequiredError(
                self.id,
                f"Evidence targets different task {evidence.target_task_id}",
            )

        if not evidence.is_verified():
            raise EvidenceRequiredError(
                self.id,
                f"Evidence status '{evidence.verification_status.value}' unverified",
            )

        old_status = self.status
        self.status = TaskStatus.COMPLETED
        current_time = when or datetime.now(UTC)
        self.completed_at = current_time
        self.evidence_records.append(evidence.id)
        self._touch(current_time)

        self._record_event(
            TaskCompletedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                evidence_id=evidence.id,
                verifier_identity=evidence.verifier_identity,
                verification_status=evidence.verification_status.value,
            )
        )
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
            )
        )

    def fail(
        self,
        reason: str,
        recovery_suggestion: str | None = None,
        when: datetime | None = None,
    ) -> None:
        """Mark task as failed while preserving context for recovery."""
        if self.status not in (TaskStatus.IN_PROGRESS, TaskStatus.AWAITING_APPROVAL):
            raise InvalidStateTransitionError(self.status.value, TaskStatus.FAILED.value)

        old_status = self.status
        self.status = TaskStatus.FAILED
        self.failure_reason = reason
        self.recovery_suggestion = recovery_suggestion
        self._touch(when)

        self._record_event(
            TaskFailedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                failure_reason=reason,
                recovery_suggestion=recovery_suggestion,
            )
        )
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason=reason,
            )
        )

    def retry(self, when: datetime | None = None) -> None:
        """Retry a failed task, resuming execution with cleared failure context."""
        if self.status != TaskStatus.FAILED:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.IN_PROGRESS.value)

        old_status = self.status
        self.status = TaskStatus.IN_PROGRESS
        self.failure_reason = None
        self.recovery_suggestion = None
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason="Task retried",
            )
        )

    def replan(self, when: datetime | None = None) -> None:
        """Revert a failed task to PLANNED for re-decomposition."""
        if self.status != TaskStatus.FAILED:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.PLANNED.value)

        old_status = self.status
        self.status = TaskStatus.PLANNED
        self.failure_reason = None
        self.recovery_suggestion = None
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason="Task reset for replanning",
            )
        )

    def defer(
        self,
        until: datetime,
        reason: str | None = None,
        when: datetime | None = None,
    ) -> None:
        """Reschedule a task without guilt, shame, or penalty."""
        if self.status not in (
            TaskStatus.PLANNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.DEFERRED,
        ):
            raise InvalidStateTransitionError(self.status.value, TaskStatus.DEFERRED.value)

        old_status = self.status
        self.status = TaskStatus.DEFERRED
        self.deferred_until = until
        self.deferral_count += 1
        self._touch(when)

        self._record_event(
            TaskDeferredEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                deferred_until=until,
                deferral_count=self.deferral_count,
                reason=reason,
            )
        )
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason=reason,
            )
        )

    def reactivate(self, when: datetime | None = None) -> None:
        """Reactivate a deferred task when its schedule arrives or is pulled forward."""
        if self.status != TaskStatus.DEFERRED:
            raise InvalidStateTransitionError(self.status.value, TaskStatus.PLANNED.value)

        old_status = self.status
        self.status = TaskStatus.PLANNED
        self.deferred_until = None
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason="Task reactivated from deferral",
            )
        )

    def cancel(self, reason: str | None = None, when: datetime | None = None) -> None:
        """Deliberately abandon a task.

        Terminal states (COMPLETED, CANCELLED) cannot be cancelled.
        """
        if self.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            raise InvalidStateTransitionError(self.status.value, TaskStatus.CANCELLED.value)

        old_status = self.status
        self.status = TaskStatus.CANCELLED
        self._touch(when)
        self._record_event(
            TaskStatusChangedEvent(
                owner_id=self.owner_id,
                aggregate_id=self.id,
                from_status=old_status.value,
                to_status=self.status.value,
                reason=reason,
            )
        )

    # -------------------------------------------------------------------------
    # Next Action Management
    # -------------------------------------------------------------------------

    def add_next_action(
        self,
        description: str,
        tool_hint: str | None = None,
        tool_args_hint: dict[str, Any] | None = None,
        risk_level: ActionRiskLevel = ActionRiskLevel.READ_ONLY,
        sort_order: int | None = None,
    ) -> NextAction:
        """Append a small, concrete action step."""
        order = sort_order if sort_order is not None else len(self.next_actions)
        action = NextAction(
            task_id=self.id,
            owner_id=self.owner_id,
            description=description,
            tool_hint=tool_hint,
            tool_args_hint=tool_args_hint,
            risk_level=risk_level,
            sort_order=order,
        )
        self.next_actions.append(action)
        self._touch()
        return action

    def get_current_next_action(self) -> NextAction | None:
        """Return the lowest sort_order incomplete next action."""
        uncompleted = [a for a in self.next_actions if not a.completed]
        if not uncompleted:
            return None
        return min(uncompleted, key=lambda a: a.sort_order)

    # -------------------------------------------------------------------------
    # Dependency Management
    # -------------------------------------------------------------------------

    def add_dependency(
        self,
        depends_on_task_id: UUID,
        dependency_type: DependencyType = DependencyType.BLOCKS,
    ) -> Dependency:
        """Declare that this task depends on prerequisite depends_on_task_id."""
        for existing in self.dependencies:
            if (
                existing.depends_on_task_id == depends_on_task_id
                and existing.dependency_type == dependency_type
            ):
                return existing

        dep = Dependency(
            task_id=self.id,
            depends_on_task_id=depends_on_task_id,
            dependency_type=dependency_type,
        )
        self.dependencies.append(dep)
        self._touch()
        return dep
