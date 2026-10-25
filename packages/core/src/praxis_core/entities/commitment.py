"""Commitment entity representing captured natural language intentions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from praxis_core.entities.common import SourceChannel


class Commitment(BaseModel):
    """The raw captured intention before or alongside structured task decomposition.

    Preserves the original user wording, capture channel, and interpretation history.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    owner_id: str
    raw_text: str
    source: SourceChannel = SourceChannel.WEB
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    idempotency_key: str | None = None
    idempotency_fingerprint: str | None = None
    interpretation_revision: int = Field(default=1)
    interpreted_intent: str | None = None
    interpretation_history: list[dict[str, Any]] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_prompt: str | None = None

    def record_interpretation(self, intent: str, metadata: dict[str, Any] | None = None) -> None:
        """Update interpreted intent and append to history, bumping revision."""
        self.interpretation_revision += 1
        self.interpreted_intent = intent
        self.interpretation_history.append(
            {
                "intent": intent,
                "recorded_at": datetime.now(UTC).isoformat(),
                "metadata": metadata or {},
                "revision": self.interpretation_revision,
            }
        )
        self.clarification_needed = False
        self.clarification_prompt = None

    def request_clarification(self, prompt: str) -> None:
        """Mark that essential details are missing and require user clarification."""
        self.interpretation_revision += 1
        self.clarification_needed = True
        self.clarification_prompt = prompt
        self.interpretation_history.append(
            {
                "clarification_requested": prompt,
                "recorded_at": datetime.now(UTC).isoformat(),
                "revision": self.interpretation_revision,
            }
        )
