"""Use case for providing clarification to an ambiguous commitment.

Leverages the core CommitmentIntakeEngine to provide high depth and transactional
integrity at the intake seam.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from praxis_core.intake.contract import ClarificationRequest, IntakeStatus
from praxis_core.intake.engine import CommitmentIntakeEngine
from praxis_core.ports.clock import Clock, SystemClock
from praxis_core.ports.task_extractor import TaskExtractor
from praxis_core.ports.unit_of_work import UnitOfWork
from praxis_core.use_cases.capture_commitment import CaptureCommitmentResult


class ClarifyCommitmentCommand(BaseModel):
    """Command input for submitting clarification to a commitment."""

    commitment_id: UUID
    owner_id: str
    clarification_response: str
    user_timezone: str = "UTC"
    reference_time: datetime | None = None


class ClarifyCommitmentUseCase:
    """Updates an ambiguous commitment with clarification and re-extracts structured task."""

    def __init__(
        self,
        uow: UnitOfWork,
        extractor: TaskExtractor,
        clock: Clock | None = None,
        engine: CommitmentIntakeEngine | None = None,
    ) -> None:
        self.uow = uow
        self.extractor = extractor
        self.clock = clock or SystemClock()
        self.engine = engine or CommitmentIntakeEngine(
            uow=uow,
            extractor=extractor,
            clock=self.clock,
        )

    async def execute(self, cmd: ClarifyCommitmentCommand) -> CaptureCommitmentResult:
        """Execute commitment clarification through the intake engine seam."""
        req = ClarificationRequest(
            commitment_id=cmd.commitment_id,
            owner_id=cmd.owner_id,
            clarification_response=cmd.clarification_response,
            user_timezone=cmd.user_timezone,
            reference_time=cmd.reference_time,
        )
        outcome = await self.engine.clarify(req)
        return CaptureCommitmentResult(
            commitment=outcome.commitment,
            task=outcome.task,
            next_action=outcome.next_action,
            clarification_needed=(outcome.status == IntakeStatus.AWAITING_CLARIFICATION),
            clarification_prompt=outcome.clarification_prompt,
        )
