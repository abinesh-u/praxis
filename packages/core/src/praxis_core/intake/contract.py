"""Intake contracts and outcome specifications for commitment intake.

This module defines the public interface, command structures, and outcome types
at the core intake seam. Adapters at the CLI or HTTP edge leverage these contracts
to achieve high locality and depth without bypassing aggregate invariants.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import SourceChannel
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task


class IntakeStatus(StrEnum):
    """Lifecycle status for a commitment intake attempt."""

    CREATED = "created"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    IN_PROGRESS = "in_progress"
    REPLAYED = "replayed"
    FAILED = "failed"


class IntakeRequest(BaseModel):
    """Command specification for capturing a natural language commitment."""

    owner_id: str
    raw_text: str
    source: SourceChannel = SourceChannel.WEB
    user_timezone: str = "UTC"
    idempotency_key: str | None = None
    reference_time: datetime | None = None

    def canonical_fingerprint(self) -> str:
        """Compute deterministic SHA-256 fingerprint over normalized text and context.

        Protects against idempotency key tampering or reuse across divergent text.
        """
        normalized_text = " ".join(self.raw_text.strip().split())
        normalized_source = self.source.value.strip().lower()
        normalized_tz = self.user_timezone.strip().lower()
        raw_material = f"{normalized_text}|{normalized_source}|{normalized_tz}"
        return hashlib.sha256(raw_material.encode("utf-8")).hexdigest()


class ClarificationRequest(BaseModel):
    """Command specification for clarifying an ambiguous commitment."""

    commitment_id: UUID | str
    owner_id: str
    clarification_response: str
    user_timezone: str = "UTC"
    reference_time: datetime | None = None


class IntakeOutcome(BaseModel):
    """Typed domain outcome returned by the commitment intake engine."""

    status: IntakeStatus
    commitment: Commitment
    task: Task | None = None
    next_action: NextAction | None = None
    clarification_prompt: str | None = None
    is_replay: bool = False
