"""Use case for capturing commitments and decomposing into tasks with next actions.

Leverages the core CommitmentIntakeEngine to provide high depth and transactional
integrity at the intake seam.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import SourceChannel
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.intake.contract import IntakeRequest, IntakeStatus
from praxis_core.intake.engine import CommitmentIntakeEngine
from praxis_core.ports.clock import Clock, SystemClock
from praxis_core.ports.task_extractor import TaskExtractor
from praxis_core.ports.unit_of_work import UnitOfWork


class CaptureCommitmentCommand(BaseModel):
    """Command input for capturing a natural language commitment."""

    owner_id: str
    raw_text: str
    source: SourceChannel = SourceChannel.WEB
    user_timezone: str = "UTC"
    idempotency_key: str | None = None
    reference_time: datetime | None = None


class CaptureCommitmentResult(BaseModel):
    """Result of commitment capture and extraction."""

    commitment: Commitment
    task: Task | None = None
    next_action: NextAction | None = None
    clarification_needed: bool = False
    clarification_prompt: str | None = None


class CaptureCommitmentUseCase:
    """Orchestrates natural language capture, extraction, and aggregate assembly."""

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

    async def execute(self, cmd: CaptureCommitmentCommand) -> CaptureCommitmentResult:
        """Execute commitment capture through the intake engine seam."""
        req = IntakeRequest(
            owner_id=cmd.owner_id,
            raw_text=cmd.raw_text,
            source=cmd.source,
            user_timezone=cmd.user_timezone,
            idempotency_key=cmd.idempotency_key,
            reference_time=cmd.reference_time,
        )
        outcome = await self.engine.capture(req)
        return CaptureCommitmentResult(
            commitment=outcome.commitment,
            task=outcome.task,
            next_action=outcome.next_action,
            clarification_needed=(outcome.status == IntakeStatus.AWAITING_CLARIFICATION),
            clarification_prompt=outcome.clarification_prompt,
        )
