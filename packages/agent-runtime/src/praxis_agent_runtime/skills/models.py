"""Procedural skill data module defining interfaces for persistent instructions.

Includes candidate validation and isolation perimeters across the seam.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SkillStatus = Literal["candidate", "validated", "rejected"]


class Skill(BaseModel):
    """A procedural skill module: instructions leveraged across agent execution depth."""

    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    instructions: str = ""
    status: SkillStatus = "validated"
    provenance: dict[str, Any] | None = None
    validation_notes: str | None = None

    @property
    def is_validated(self) -> bool:
        """Return True if this skill is validated for active prompt depth injection."""
        return self.status == "validated"

    @property
    def is_candidate(self) -> bool:
        """Return True if this skill is an untrusted candidate pending validation."""
        return self.status == "candidate"
