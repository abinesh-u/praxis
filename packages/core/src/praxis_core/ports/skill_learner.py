"""Skill learner port interface module.

Defines the contract for distilling candidate procedural skills from verified executions
across the validation seam, preserving operational depth and tenant locality.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from praxis_core.entities.evidence import Evidence


class SkillLearner(Protocol):
    """Port interface for distilling candidate procedural knowledge from verified runs.

    Coordinates extraction across the execution seam while enforcing candidate quarantine
    to prevent unverified instructions from gaining active execution privileges.
    """

    def learn_from_execution(
        self,
        *,
        attempt_id: UUID,
        task_id: UUID,
        owner_id: str,
        evidence: Evidence,
        raw_payload: Any,
        action_description: str | None = None,
    ) -> Any | None:
        """Evaluate a completed execution attempt to extract an isolated candidate skill.

        Returns the extracted candidate skill metadata, or None if the run is ineligible.
        """
        ...
