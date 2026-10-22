"""Evidence entity for recording observable proof of execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from praxis_core.entities.common import EvidenceSource, VerificationStatus


class Evidence(BaseModel):
    """An observable record of what occurred during an action or task completion.

    Design principle: Evidence records what was observed; verification establishes
    what that observation supports.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    source: EvidenceSource
    verification_status: VerificationStatus
    verifier_identity: str  # e.g., "tool:workspace_fs.write_file", "user:abi"
    target_task_id: UUID
    target_action_id: UUID | None = None
    target_run_id: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: str | None = None  # Reference to persistent artifact or hash

    model_config = {"frozen": True}

    def is_verified(self) -> bool:
        """Return True if evidence meets verified standards (not an unverified assertion)."""
        return self.verification_status in (
            VerificationStatus.MACHINE_VERIFIED,
            VerificationStatus.HUMAN_CONFIRMED,
        )

    @classmethod
    def machine_verified(
        cls,
        target_task_id: UUID,
        verifier_identity: str,
        details: dict[str, Any],
        target_action_id: UUID | None = None,
        target_run_id: str | None = None,
        artifact_ref: str | None = None,
    ) -> Evidence:
        """Factory for machine-observed proof (checksum, process returncode, API receipt)."""
        return cls(
            source=EvidenceSource.TOOL,
            verification_status=VerificationStatus.MACHINE_VERIFIED,
            verifier_identity=verifier_identity,
            target_task_id=target_task_id,
            target_action_id=target_action_id,
            target_run_id=target_run_id,
            details=details,
            artifact_ref=artifact_ref,
        )

    @classmethod
    def human_confirmed(
        cls,
        target_task_id: UUID,
        user_identity: str,
        confirmation_note: str,
        target_action_id: UUID | None = None,
    ) -> Evidence:
        """Factory for legitimate human confirmation without pretending to have machine proof."""
        return cls(
            source=EvidenceSource.USER,
            verification_status=VerificationStatus.HUMAN_CONFIRMED,
            verifier_identity=user_identity,
            target_task_id=target_task_id,
            target_action_id=target_action_id,
            details={"note": confirmation_note},
        )
