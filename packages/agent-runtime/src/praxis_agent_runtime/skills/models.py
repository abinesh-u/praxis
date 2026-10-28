"""Procedural skill data module defining interfaces for persistent instructions.

Includes candidate validation, review audit, and isolation perimeters across the seam.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SkillStatus = Literal["candidate", "validated", "rejected"]


class ReviewAudit(BaseModel):
    """Audit record documenting an operator's explicit review decision."""

    decision: Literal["promoted", "rejected"]
    operator_id: str
    timestamp: str
    notes: str | None = None


class SkillCollisionError(ValueError):
    """Raised when two distinct skill names collide on the same storage slug."""


class InvalidStateTransitionError(ValueError):
    """Raised when attempting an invalid skill lifecycle state transition."""


class SkillSecurityError(ValueError):
    """Raised when a skill violates storage containment or safety policies."""


class Skill(BaseModel):
    """A procedural skill module: instructions leveraged across agent execution depth."""

    id: str | None = None
    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    instructions: str = ""
    status: SkillStatus = "validated"
    provenance: dict[str, Any] | None = None
    review_audit: ReviewAudit | None = None
    validation_notes: str | None = None

    @property
    def is_validated(self) -> bool:
        """Return True if this skill is validated for active prompt depth injection."""
        return self.status == "validated"

    @property
    def is_candidate(self) -> bool:
        """Return True if this skill is an untrusted candidate pending validation."""
        return self.status == "candidate"

    @property
    def is_rejected(self) -> bool:
        """Return True if this skill has been explicitly rejected/archived."""
        return self.status == "rejected"

    @property
    def owner_id(self) -> str | None:
        """Return the tenant owner identity associated with this skill provenance locality."""
        if self.provenance and isinstance(self.provenance, dict):
            return self.provenance.get("owner_id")
        return None

    @property
    def attempt_id(self) -> str | None:
        """Return the execution attempt ID associated with this candidate across the seam."""
        if self.provenance and isinstance(self.provenance, dict):
            return self.provenance.get("attempt_id")
        return None
