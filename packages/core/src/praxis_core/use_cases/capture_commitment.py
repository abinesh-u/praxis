"""Use case for capturing commitments and decomposing into tasks with next actions."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import SourceChannel
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
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
    """Orchestrates natural language capture, AI extraction, and aggregate assembly."""

    def __init__(
        self,
        uow: UnitOfWork,
        extractor: TaskExtractor,
        clock: Clock | None = None,
    ) -> None:
        self.uow = uow
        self.extractor = extractor
        self.clock = clock or SystemClock()

    async def execute(self, cmd: CaptureCommitmentCommand) -> CaptureCommitmentResult:
        ref_time = cmd.reference_time or self.clock.now()
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=UTC)

        async with self.uow:
            if cmd.idempotency_key:
                existing_c = await self.uow.commitments.find_by_idempotency_key(
                    cmd.idempotency_key,
                    cmd.owner_id,
                )
                if existing_c is not None:
                    all_tasks = await self.uow.tasks.list_by_owner(cmd.owner_id)
                    matched_task = next(
                        (t for t in all_tasks if t.commitment_id == existing_c.id),
                        None,
                    )
                    next_act = matched_task.get_current_next_action() if matched_task else None
                    return CaptureCommitmentResult(
                        commitment=existing_c,
                        task=matched_task,
                        next_action=next_act,
                        clarification_needed=existing_c.clarification_needed,
                        clarification_prompt=existing_c.clarification_prompt,
                    )

            commitment = Commitment(
                owner_id=cmd.owner_id,
                raw_text=cmd.raw_text,
                source=cmd.source,
                captured_at=ref_time,
                idempotency_key=cmd.idempotency_key,
            )
            await self.uow.commitments.save(commitment)

            extracted = await self.extractor.extract(
                cmd.raw_text,
                reference_time=ref_time,
                user_timezone=cmd.user_timezone,
            )

            if extracted.clarification_needed:
                prompt = (
                    extracted.clarification_prompt
                    or "Could you clarify the specific details of this commitment?"
                )
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
                {"priority": extracted.priority.value},
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
