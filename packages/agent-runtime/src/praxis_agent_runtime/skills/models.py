"""Skill data model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """A procedural skill: a reusable set of instructions the agent can follow."""

    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    instructions: str = ""
