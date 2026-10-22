"""Unit tests verifying evidence provenance, verification levels, and decoupled action tracking."""

from uuid import uuid4

import pytest
from praxis_core.entities.common import (
    EvidenceSource,
    VerificationStatus,
)
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import Task
from praxis_core.errors import EvidenceRequiredError


@pytest.fixture
def sample_task() -> Task:
    task = Task(owner_id="user_123", title="Clean up workspace artifacts")
    task.start()
    return task


class TestEvidenceProvenanceAndVerification:
    """Verifies evidence creation, verification levels, and completion guards."""

    def test_machine_verified_evidence_satisfies_completion(self, sample_task: Task):
        evidence = Evidence.machine_verified(
            target_task_id=sample_task.id,
            verifier_identity="tool:workspace_fs.rm",
            details={"deleted_count": 5, "root": "/workspace/tmp"},
            artifact_ref="sha256:abc123def456",
        )
        assert evidence.is_verified() is True
        assert evidence.source == EvidenceSource.TOOL
        assert evidence.verification_status == VerificationStatus.MACHINE_VERIFIED

        sample_task.complete(evidence=evidence)
        assert sample_task.completed_at is not None
        assert evidence.id in sample_task.evidence_records

    def test_human_confirmed_evidence_satisfies_completion(self, sample_task: Task):
        """Legitimate human-confirmed tasks succeed without synthesizing fake machine proof."""
        evidence = Evidence.human_confirmed(
            target_task_id=sample_task.id,
            user_identity="user:abi",
            confirmation_note="Personally verified medication taken",
        )
        assert evidence.is_verified() is True
        assert evidence.source == EvidenceSource.USER
        assert evidence.verification_status == VerificationStatus.HUMAN_CONFIRMED

        sample_task.complete(evidence=evidence)
        assert sample_task.completed_at is not None

    def test_unverified_assertion_rejected_for_completion(self, sample_task: Task):
        unverified = Evidence(
            source=EvidenceSource.TOOL,
            verification_status=VerificationStatus.UNVERIFIED_ASSERTION,
            verifier_identity="untrusted_script",
            target_task_id=sample_task.id,
            details={"claim": "done"},
        )
        assert unverified.is_verified() is False

        with pytest.raises(EvidenceRequiredError) as exc_info:
            sample_task.complete(evidence=unverified)
        assert "unverified" in str(exc_info.value)


class TestNextActionDecoupling:
    """Verifies that task completion does not falsely synthesize proof for unexecuted actions."""

    def test_unexecuted_next_actions_remain_uncompleted_on_task_complete(self, sample_task: Task):
        action1 = sample_task.add_next_action(description="Find temporary files", sort_order=0)
        action2 = sample_task.add_next_action(description="Delete temporary files", sort_order=1)
        action3 = sample_task.add_next_action(description="Verify free space", sort_order=2)

        # Action 1 is executed and completed
        action1.mark_completed(evidence_id=uuid4())
        assert action1.completed is True
        assert action2.completed is False
        assert action3.completed is False

        # Task completes via overall evidence
        overall_evidence = Evidence.machine_verified(
            target_task_id=sample_task.id,
            verifier_identity="system_audit",
            details={"verified": True},
        )
        sample_task.complete(overall_evidence)

        # Invariant: Actions 2 and 3 must NOT be marked completed
        assert action2.completed is False
        assert action3.completed is False

    def test_next_action_attempt_tracking(self, sample_task: Task):
        action = sample_task.add_next_action(description="Fetch API data")
        assert action.execution_attempts == 0
        assert action.last_attempt_at is None

        action.record_attempt()
        assert action.execution_attempts == 1
        assert action.last_attempt_at is not None

        action.record_attempt()
        assert action.execution_attempts == 2

    def test_get_current_next_action_returns_lowest_sort_order_uncompleted(self, sample_task: Task):
        action1 = sample_task.add_next_action("Step A", sort_order=10)
        action2 = sample_task.add_next_action("Step B", sort_order=5)
        action3 = sample_task.add_next_action("Step C", sort_order=20)

        # Lowest sort_order is action2 (sort_order=5)
        assert sample_task.get_current_next_action() == action2

        action2.mark_completed()
        # Next lowest is action1 (sort_order=10)
        assert sample_task.get_current_next_action() == action1

        action1.mark_completed()
        assert sample_task.get_current_next_action() == action3

        action3.mark_completed()
        assert sample_task.get_current_next_action() is None
