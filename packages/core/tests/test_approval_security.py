"""Unit tests verifying action-bound approval security, token hashing, and atomic consumption."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus
from praxis_core.errors import (
    ApprovalActionMismatchError,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    InvalidApprovalError,
)


@pytest.fixture
def sample_action() -> ActionSpecification:
    return ActionSpecification(
        tool_name="fs_write_file",
        canonical_args={"path": "/workspace/config.json", "content": '{"active": true}'},
        task_id=uuid4(),
        run_id="run_abc123",
        permission_scope="workspace_write",
    )


class TestActionFingerprinting:
    """Verifies cryptographic fingerprinting of action specifications."""

    def test_fingerprint_deterministic_and_key_order_independent(self):
        task_id = uuid4()
        action1 = ActionSpecification(
            tool_name="shell_run",
            canonical_args={"command": "npm install", "timeout": 30},
            task_id=task_id,
        )
        action2 = ActionSpecification(
            tool_name="shell_run",
            canonical_args={"timeout": 30, "command": "npm install"},  # Reversed key order
            task_id=task_id,
        )
        assert action1.fingerprint() == action2.fingerprint()

    def test_fingerprint_changes_on_argument_tampering(self, sample_action: ActionSpecification):
        original_fp = sample_action.fingerprint()
        tampered_action = ActionSpecification(
            tool_name=sample_action.tool_name,
            canonical_args={"path": "/workspace/other_file.json", "content": '{"active": true}'},
            task_id=sample_action.task_id,
            run_id=sample_action.run_id,
            permission_scope=sample_action.permission_scope,
        )
        assert original_fp != tampered_action.fingerprint()


class TestApprovalSecurityAndLifecycle:
    """Verifies token generation, hashing, and consumption invariants."""

    def test_token_hash_stored_not_plaintext(self, sample_action: ActionSpecification):
        req, raw_token = ApprovalRequest.create(
            owner_id="user_123",
            task_id=sample_action.task_id,
            action=sample_action,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Write config file",
        )
        # Bearer token is returned
        assert isinstance(raw_token, str)
        assert len(raw_token) > 20
        # Entity does not store raw token
        assert not hasattr(req, "token")
        # Token hash is SHA-256 of raw token
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert req.token_hash == expected_hash

    def test_consume_valid_approval_succeeds(self, sample_action: ActionSpecification):
        req, raw_token = ApprovalRequest.create(
            owner_id="user_123",
            task_id=sample_action.task_id,
            action=sample_action,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Write config",
        )
        req.approve(decided_by="user_123")
        assert req.status == ApprovalStatus.APPROVED

        # Consume with exact action and token
        req.consume(presented_token=raw_token, action=sample_action)
        assert req.status == ApprovalStatus.CONSUMED

    def test_single_use_invariant_violating_second_consumption_fails(
        self, sample_action: ActionSpecification
    ):
        req, raw_token = ApprovalRequest.create(
            owner_id="user_123",
            task_id=sample_action.task_id,
            action=sample_action,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Write config",
        )
        req.approve(decided_by="user_123")
        req.consume(presented_token=raw_token, action=sample_action)

        # Second attempt must fail
        with pytest.raises(ApprovalAlreadyConsumedError):
            req.consume(presented_token=raw_token, action=sample_action)

    def test_tampered_action_fails_consumption(self, sample_action: ActionSpecification):
        req, raw_token = ApprovalRequest.create(
            owner_id="user_123",
            task_id=sample_action.task_id,
            action=sample_action,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Write config",
        )
        req.approve(decided_by="user_123")

        tampered_action = ActionSpecification(
            tool_name=sample_action.tool_name,
            canonical_args={"path": "/etc/passwd"},  # Tampered arguments!
            task_id=sample_action.task_id,
        )

        with pytest.raises(ApprovalActionMismatchError):
            req.consume(presented_token=raw_token, action=tampered_action)
        # Status should NOT be marked consumed if validation failed
        assert req.status == ApprovalStatus.APPROVED

    def test_expired_approval_cannot_be_approved_or_consumed(
        self, sample_action: ActionSpecification
    ):
        req, raw_token = ApprovalRequest.create(
            owner_id="user_123",
            task_id=sample_action.task_id,
            action=sample_action,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Write config",
            expires_in_seconds=60,
        )
        past_expiry = req.expires_at + timedelta(seconds=1)

        with pytest.raises(ApprovalExpiredError):
            req.approve(decided_by="user_123", when=past_expiry)
        assert req.status == ApprovalStatus.EXPIRED

    def test_unapproved_request_cannot_be_consumed(self, sample_action: ActionSpecification):
        req, raw_token = ApprovalRequest.create(
            owner_id="user_123",
            task_id=sample_action.task_id,
            action=sample_action,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Write config",
        )
        with pytest.raises(InvalidApprovalError):
            req.consume(presented_token=raw_token, action=sample_action)
