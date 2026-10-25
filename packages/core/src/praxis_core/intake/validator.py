"""Deterministic proposal validation module for commitment intake.

This module validates proposed extractions before aggregate construction.
It isolates deterministic checks from model inference, ensuring that malformed
or incomplete model proposals never violate domain invariants.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from praxis_core.entities.common import Priority
from praxis_core.errors import IntakeValidationError
from praxis_core.ports.task_extractor import ExtractedTaskData


class ValidatedProposal(BaseModel):
    """Validated task and next action proposal ready for aggregate assembly."""

    title: str
    description: str = ""
    priority: Priority = Priority.ROUTINE
    due_date: datetime | None = None
    scheduled_date: datetime | None = None
    next_action_description: str = ""
    suggested_tool_hint: str | None = None
    suggested_tool_args: dict[str, Any] = Field(default_factory=dict)
    clarification_needed: bool = False
    clarification_prompt: str | None = None


class IntakeProposalValidator:
    """Validates raw extracted task proposals against deterministic domain rules.

    Provides depth and locality by encapsulating sanitization, temporal grounding,
    and invariant checks without instantiating domain aggregates.
    """

    def validate(
        self,
        proposal: ExtractedTaskData,
        reference_time: datetime,
        user_timezone: str = "UTC",
    ) -> ValidatedProposal:
        """Validate extraction proposal against deterministic constraints."""
        if proposal.clarification_needed:
            prompt = (
                proposal.clarification_prompt.strip()
                if proposal.clarification_prompt
                else "Could you clarify the specific details of this commitment?"
            )
            return ValidatedProposal(
                title=proposal.title.strip() if proposal.title else "",
                description=proposal.description.strip() if proposal.description else "",
                clarification_needed=True,
                clarification_prompt=prompt,
            )

        title = proposal.title.strip() if proposal.title else ""
        if not title:
            raise IntakeValidationError("Task title cannot be empty")

        next_action = (
            proposal.next_action_description.strip() if proposal.next_action_description else ""
        )
        if not next_action:
            raise IntakeValidationError("Next action description cannot be empty")

        if not isinstance(proposal.priority, Priority):
            try:
                priority = Priority(proposal.priority)
            except ValueError as exc:
                raise IntakeValidationError(f"Invalid priority: {proposal.priority}") from exc
        else:
            priority = proposal.priority

        due_date = self._normalize_datetime(proposal.due_date, user_timezone)
        scheduled_date = self._normalize_datetime(proposal.scheduled_date, user_timezone)

        tool_args = (
            proposal.suggested_tool_args if isinstance(proposal.suggested_tool_args, dict) else {}
        )

        return ValidatedProposal(
            title=title,
            description=proposal.description.strip() if proposal.description else "",
            priority=priority,
            due_date=due_date,
            scheduled_date=scheduled_date,
            next_action_description=next_action,
            suggested_tool_hint=proposal.suggested_tool_hint,
            suggested_tool_args=tool_args,
            clarification_needed=False,
            clarification_prompt=None,
        )

    def _normalize_datetime(
        self,
        dt: datetime | None,
        user_timezone: str,
    ) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt
        try:
            tz = ZoneInfo(user_timezone)
            return dt.replace(tzinfo=tz)
        except ZoneInfoNotFoundError:
            return dt.replace(tzinfo=UTC)
