"""ApprovalRequest entity binding cryptographically secure authorization to exact actions."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from praxis_core.entities.common import (
    ActionRiskLevel,
    ApprovalStatus,
    canonicalize_arguments,
)
from praxis_core.errors import (
    ApprovalActionMismatchError,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    InvalidApprovalError,
)


class ActionSpecification(BaseModel):
    """Immutable specification of the exact action requesting approval."""

    tool_name: str
    canonical_args: dict[str, Any] = Field(default_factory=dict)
    task_id: UUID
    run_id: str | None = None
    permission_scope: str = "default"

    model_config = {"frozen": True}

    def fingerprint(self) -> str:
        """Compute a deterministic SHA-256 fingerprint of the action parameters."""
        canonical_json = canonicalize_arguments(self.canonical_args)
        payload = (
            f"{self.tool_name}|{canonical_json}|{self.task_id}|"
            f"{self.run_id or ''}|{self.permission_scope}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ApprovalRequest(BaseModel):
    """A time-bounded, action-bound decision authorizing a specific operation.

    Security guarantees:
    1. Binds to an exact action fingerprint (preventing argument tampering).
    2. Stores only the SHA-256 hash of the bearer token, never the plaintext token.
    3. Enforces single-use atomic consumption.
    4. Enforces strict expiration.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    owner_id: str
    task_id: UUID
    action: ActionSpecification
    action_fingerprint: str
    risk_level: ActionRiskLevel
    justification: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    token_hash: str  # SHA-256 of the one-time token
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    rejection_reason: str | None = None

    @classmethod
    def create(
        cls,
        owner_id: str,
        task_id: UUID,
        action: ActionSpecification,
        risk_level: ActionRiskLevel,
        justification: str,
        expires_in_seconds: int = 3600,
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, str]:
        """Create an approval request and generate a single-use token.

        Returns:
            tuple[ApprovalRequest, str]: The entity (with hashed token) and the raw bearer token.
        """
        current_time = now or datetime.now(UTC)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = current_time + timedelta(seconds=expires_in_seconds)

        request = cls(
            owner_id=owner_id,
            task_id=task_id,
            action=action,
            action_fingerprint=action.fingerprint(),
            risk_level=risk_level,
            justification=justification,
            token_hash=token_hash,
            requested_at=current_time,
            expires_at=expires_at,
        )
        return request, raw_token

    def approve(self, decided_by: str, when: datetime | None = None) -> None:
        """Grant approval for the action."""
        current_time = when or datetime.now(UTC)
        if current_time > self.expires_at:
            self.status = ApprovalStatus.EXPIRED
            raise ApprovalExpiredError(self.id, self.expires_at)
        if self.status != ApprovalStatus.PENDING:
            raise InvalidApprovalError(self.id, f"Cannot approve request in status '{self.status}'")

        self.status = ApprovalStatus.APPROVED
        self.decided_by = decided_by
        self.decided_at = current_time

    def reject(self, decided_by: str, reason: str, when: datetime | None = None) -> None:
        """Deny approval for the action."""
        current_time = when or datetime.now(UTC)
        if self.status != ApprovalStatus.PENDING:
            raise InvalidApprovalError(self.id, f"Cannot reject request in status '{self.status}'")

        self.status = ApprovalStatus.REJECTED
        self.decided_by = decided_by
        self.decided_at = current_time
        self.rejection_reason = reason

    def is_active(self, at: datetime | None = None) -> bool:
        """Check if approval is currently valid and unexpired."""
        current_time = at or datetime.now(UTC)
        is_pending_or_approved = self.status in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
        return is_pending_or_approved and current_time <= self.expires_at

    def consume(
        self,
        presented_token: str,
        action: ActionSpecification,
        at: datetime | None = None,
    ) -> None:
        """Validate and atomically consume the approval for execution.

        Raises:
            ApprovalAlreadyConsumedError: If already consumed.
            ApprovalExpiredError: If expired.
            InvalidApprovalError: If not approved or token invalid.
            ApprovalActionMismatchError: If action parameters differ from what was approved.
        """
        current_time = at or datetime.now(UTC)

        if self.status == ApprovalStatus.CONSUMED:
            raise ApprovalAlreadyConsumedError(self.id)

        if current_time > self.expires_at:
            self.status = ApprovalStatus.EXPIRED
            raise ApprovalExpiredError(self.id, self.expires_at)

        if self.status != ApprovalStatus.APPROVED:
            raise InvalidApprovalError(
                self.id,
                f"Cannot consume approval with status '{self.status}'",
            )

        presented_hash = hashlib.sha256(presented_token.encode("utf-8")).hexdigest()
        if not secrets.compare_digest(presented_hash, self.token_hash):
            raise InvalidApprovalError(self.id, "Invalid token credentials")

        current_fingerprint = action.fingerprint()
        if not secrets.compare_digest(current_fingerprint, self.action_fingerprint):
            raise ApprovalActionMismatchError(self.action_fingerprint, current_fingerprint)

        self.status = ApprovalStatus.CONSUMED
