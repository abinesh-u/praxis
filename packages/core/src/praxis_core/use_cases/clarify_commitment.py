"""Use case for providing clarification to an ambiguous commitment."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError
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
    ) -> None:
        self.uow = uow
        self.extractor = extractor
        self.clock = clock or SystemClock()

    async def execute(self, cmd: ClarifyCommitmentCommand) -> CaptureCommitmentResult:
        ref_time = cmd.reference_time or self.clock.now()
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=UTC)

        async with self.uow:
            commitment = await self.uow.commitments.get_for_owner(
                cmd.commitment_id,
                cmd.owner_id,
            )
            if commitment is None:
                raise EntityNotFoundError("Commitment", cmd.commitment_id)

            combined_text = (
                f"{commitment.raw_text}\nUser Clarification: {cmd.clarification_response}"
            )

            extracted = await self.extractor.extract(
                combined_text,
                reference_time=ref_time,
                user_timezone=cmd.user_timezone,
            )

            if extracted.clarification_needed:
                prompt = extracted.clarification_prompt or "Further clarification needed"
                commitment.request_clarification(prompt)
                await self.uow.commitments.save(commitment)
                await self.uow.commit()
                return CaptureCommitmentResult(
                    commitment=commitment,
                    clarification_needed=True,
                    clarification_prompt=prompt,
                )

            commitment.record_interpretation(
                extracted.title,
                {"clarification": cmd.clarification_response},
            )
            await self.uow.commitments.save(commitment)

            task = Task(
                owner_id=cmd.owner_id,
                title=extracted.title,
                description=extracted.description,
                priority=extracted.priority,
                commitment_id=commitment.id,
                due_date=extracted.due_date,
                scheduled_date=extracted.scheduled_date,
            )
            action = task.add_next_action(
                description=extracted.next_action_description,
                tool_hint=extracted.suggested_tool_hint,
                tool_args_hint=extracted.suggested_tool_args,
            )

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

            return CaptureCommitmentResult(
                commitment=commitment,
                task=task,
                next_action=action,
            )
