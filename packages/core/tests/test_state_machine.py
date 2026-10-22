"""Unit tests for the complete Task state machine and lifecycle transition matrix."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from praxis_core.entities.common import Priority, TaskStatus
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import Task
from praxis_core.errors import (
    BlockedTaskError,
    EvidenceRequiredError,
    InvalidStateTransitionError,
)


@pytest.fixture
def make_task() -> Task:
    return Task(
        owner_id="user_123",
        title="File annual taxes",
        priority=Priority.IMPORTANT,
    )


@pytest.fixture
def valid_evidence(make_task: Task) -> Evidence:
    return Evidence.machine_verified(
        target_task_id=make_task.id,
        verifier_identity="tool:tax_service",
        details={"status": "accepted", "confirmation_code": "TX-9988"},
    )


class TestStateTransitionsValid:
    """Verifies every allowed transition defined in the transition matrix."""

    def test_planned_to_in_progress(self, make_task: Task):
        make_task.start()
        assert make_task.status == TaskStatus.IN_PROGRESS
        assert make_task.version == 2

    def test_planned_to_deferred(self, make_task: Task):
        until = datetime.now(UTC) + timedelta(days=2)
        make_task.defer(until=until, reason="Waiting for weekend")
        assert make_task.status == TaskStatus.DEFERRED
        assert make_task.deferred_until == until
        assert make_task.deferral_count == 1

    def test_planned_to_cancelled(self, make_task: Task):
        make_task.cancel(reason="No longer relevant")
        assert make_task.status == TaskStatus.CANCELLED

    def test_in_progress_to_awaiting_approval(self, make_task: Task):
        make_task.start()
        make_task.await_approval(reason="File write requires confirmation")
        assert make_task.status == TaskStatus.AWAITING_APPROVAL

    def test_in_progress_to_completed_with_evidence(
        self, make_task: Task, valid_evidence: Evidence
    ):
        make_task.start()
        make_task.complete(evidence=valid_evidence)
        assert make_task.status == TaskStatus.COMPLETED
        assert make_task.completed_at is not None
        assert valid_evidence.id in make_task.evidence_records

    def test_in_progress_to_failed(self, make_task: Task):
        make_task.start()
        make_task.fail(reason="Network timeout", recovery_suggestion="Retry with backoff")
        assert make_task.status == TaskStatus.FAILED
        assert make_task.failure_reason == "Network timeout"
        assert make_task.recovery_suggestion == "Retry with backoff"

    def test_in_progress_to_deferred(self, make_task: Task):
        make_task.start()
        until = datetime.now(UTC) + timedelta(hours=4)
        make_task.defer(until=until)
        assert make_task.status == TaskStatus.DEFERRED
        assert make_task.deferral_count == 1

    def test_in_progress_to_cancelled(self, make_task: Task):
        make_task.start()
        make_task.cancel(reason="User stopped run")
        assert make_task.status == TaskStatus.CANCELLED

    def test_awaiting_approval_to_in_progress_on_approval(self, make_task: Task):
        make_task.start()
        make_task.await_approval(reason="Needs confirmation")
        make_task.approval_granted()
        assert make_task.status == TaskStatus.IN_PROGRESS

    def test_awaiting_approval_to_planned_on_non_fatal_rejection(self, make_task: Task):
        make_task.start()
        make_task.await_approval(reason="Needs confirmation")
        make_task.approval_rejected(fatal=False, reason="User chose different approach")
        assert make_task.status == TaskStatus.PLANNED

    def test_awaiting_approval_to_failed_on_fatal_rejection(self, make_task: Task):
        make_task.start()
        make_task.await_approval(reason="Needs confirmation")
        make_task.approval_rejected(fatal=True, reason="Critical permission denied")
        assert make_task.status == TaskStatus.FAILED
        assert "Critical permission denied" in (make_task.failure_reason or "")

    def test_awaiting_approval_to_cancelled(self, make_task: Task):
        make_task.start()
        make_task.await_approval(reason="Needs confirmation")
        make_task.cancel(reason="Abandoned during approval")
        assert make_task.status == TaskStatus.CANCELLED

    def test_deferred_to_planned_reactivate(self, make_task: Task):
        make_task.defer(until=datetime.now(UTC) + timedelta(days=1))
        make_task.reactivate()
        assert make_task.status == TaskStatus.PLANNED
        assert make_task.deferred_until is None

    def test_deferred_to_cancelled(self, make_task: Task):
        make_task.defer(until=datetime.now(UTC) + timedelta(days=1))
        make_task.cancel()
        assert make_task.status == TaskStatus.CANCELLED

    def test_failed_to_in_progress_retry(self, make_task: Task):
        make_task.start()
        make_task.fail(reason="Transient error")
        make_task.retry()
        assert make_task.status == TaskStatus.IN_PROGRESS
        assert make_task.failure_reason is None
        assert make_task.recovery_suggestion is None

    def test_failed_to_planned_replan(self, make_task: Task):
        make_task.start()
        make_task.fail(reason="Missing credentials")
        make_task.replan()
        assert make_task.status == TaskStatus.PLANNED
        assert make_task.failure_reason is None

    def test_failed_to_cancelled(self, make_task: Task):
        make_task.start()
        make_task.fail(reason="Unrecoverable error")
        make_task.cancel()
        assert make_task.status == TaskStatus.CANCELLED


class TestTerminalStateInvariants:
    """Verifies that terminal states (COMPLETED, CANCELLED) forbid any outgoing transitions."""

    def test_completed_is_strictly_terminal(self, make_task: Task, valid_evidence: Evidence):
        make_task.start()
        make_task.complete(evidence=valid_evidence)
        assert make_task.status == TaskStatus.COMPLETED

        with pytest.raises(InvalidStateTransitionError):
            make_task.start()

        with pytest.raises(InvalidStateTransitionError):
            make_task.complete(evidence=valid_evidence)

        with pytest.raises(InvalidStateTransitionError):
            make_task.cancel()

        with pytest.raises(InvalidStateTransitionError):
            make_task.fail(reason="Cannot fail completed task")

        with pytest.raises(InvalidStateTransitionError):
            make_task.defer(until=datetime.now(UTC) + timedelta(days=1))

    def test_cancelled_is_strictly_terminal(self, make_task: Task, valid_evidence: Evidence):
        make_task.cancel(reason="Abandoned")
        assert make_task.status == TaskStatus.CANCELLED

        with pytest.raises(InvalidStateTransitionError):
            make_task.start()

        with pytest.raises(InvalidStateTransitionError):
            make_task.cancel()

        with pytest.raises(InvalidStateTransitionError):
            make_task.complete(evidence=valid_evidence)

        with pytest.raises(InvalidStateTransitionError):
            make_task.retry()


class TestStateInvariantsAndValidation:
    """Verifies preconditions, invariants, and edge conditions."""

    def test_start_blocked_task_raises_error(self, make_task: Task):
        prereq_id = uuid4()
        make_task.add_dependency(prereq_id)
        with pytest.raises(BlockedTaskError) as exc_info:
            make_task.start(is_blocked=True)
        assert exc_info.value.task_id == make_task.id
        assert prereq_id in exc_info.value.blocking_task_ids
        assert make_task.status == TaskStatus.PLANNED  # Unchanged

    def test_complete_requires_evidence_targeting_this_task(self, make_task: Task):
        other_task_id = uuid4()
        mismatched_evidence = Evidence.machine_verified(
            target_task_id=other_task_id,
            verifier_identity="tool:test",
            details={},
        )
        make_task.start()
        with pytest.raises(EvidenceRequiredError):
            make_task.complete(mismatched_evidence)
        assert make_task.status == TaskStatus.IN_PROGRESS

    def test_repeated_deferrals_increment_count_guilt_free(self, make_task: Task):
        assert make_task.deferral_count == 0
        make_task.defer(until=datetime.now(UTC) + timedelta(days=1))
        assert make_task.deferral_count == 1
        # Reschedule directly while still in DEFERRED status
        make_task.defer(until=datetime.now(UTC) + timedelta(days=3))
        assert make_task.deferral_count == 2
        assert make_task.status == TaskStatus.DEFERRED

    def test_add_dependency_deduplicates_identical_prerequisites(self, make_task: Task):
        prereq_id = uuid4()
        dep1 = make_task.add_dependency(prereq_id)
        dep2 = make_task.add_dependency(prereq_id)
        assert dep1.id == dep2.id
        assert len(make_task.dependencies) == 1
