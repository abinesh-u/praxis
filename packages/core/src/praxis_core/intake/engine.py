"""Commitment intake engine module.

Provides depth and high locality for capturing and clarifying commitments.
Isolates transactional aggregate assembly from model inference via a three-phase
execution seam, guaranteeing that external model latency never holds database locks.
Adapters at the CLI and HTTP edge leverage this engine as their primary interface.
"""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import TaskStatus
from praxis_core.entities.task import Task
from praxis_core.errors import (
    AmbiguousIdentifierError,
    EntityNotFoundError,
    IdempotencyConflictError,
    InvalidClarificationTargetError,
    StaleInferenceError,
)
from praxis_core.intake.contract import (
    ClarificationRequest,
    IntakeOutcome,
    IntakeRequest,
    IntakeStatus,
)
from praxis_core.intake.validator import IntakeProposalValidator
from praxis_core.ports.clock import Clock, SystemClock
from praxis_core.ports.task_extractor import TaskExtractor
from praxis_core.ports.unit_of_work import UnitOfWork


class CommitmentIntakeEngine:
    """Core intake engine coordinating commitment capture, validation, and clarification.

    Enforces transactional depth through a three-phase lifecycle:
    1. Phase 1 (Atomic): Persist raw intent with canonical fingerprint and revision token.
    2. Phase 2 (Non-blocking I/O): Perform model inference and validation outside write locks.
    3. Phase 3 (Atomic): Verify revision token, update aggregate, and assemble task structures.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        extractor: TaskExtractor,
        validator: IntakeProposalValidator | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.uow = uow
        self.extractor = extractor
        self.validator = validator or IntakeProposalValidator()
        self.clock = clock or SystemClock()

    async def capture(self, req: IntakeRequest) -> IntakeOutcome:
        """Capture a natural language commitment through the three-phase intake seam."""
        ref_time = req.reference_time or self.clock.now()
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=UTC)

        fingerprint = req.canonical_fingerprint()

        # Phase 1: Atomic persistence of raw commitment intent
        async with self.uow:
            if req.idempotency_key:
                existing = await self.uow.commitments.find_by_idempotency_key(
                    req.idempotency_key,
                    req.owner_id,
                )
                if existing is not None:
                    if (
                        existing.idempotency_fingerprint
                        and existing.idempotency_fingerprint != fingerprint
                    ):
                        raise IdempotencyConflictError(
                            req.idempotency_key,
                            f"Fingerprint mismatch for existing commitment {existing.id}",
                        )

                    existing_task = await self.uow.tasks.find_by_commitment_id(
                        existing.id,
                        req.owner_id,
                    )
                    if existing_task is not None:
                        return IntakeOutcome(
                            status=IntakeStatus.REPLAYED,
                            commitment=existing,
                            task=existing_task,
                            next_action=existing_task.get_current_next_action(),
                            is_replay=True,
                        )

                    if existing.clarification_needed:
                        return IntakeOutcome(
                            status=IntakeStatus.AWAITING_CLARIFICATION,
                            commitment=existing,
                            clarification_prompt=existing.clarification_prompt,
                            is_replay=True,
                        )

                    # Resumption case: commitment exists without task (interrupted inference)
                    commitment = existing
                else:
                    commitment = Commitment(
                        owner_id=req.owner_id,
                        raw_text=req.raw_text,
                        source=req.source,
                        captured_at=ref_time,
                        idempotency_key=req.idempotency_key,
                        idempotency_fingerprint=fingerprint,
                        interpretation_revision=1,
                    )
                    await self.uow.commitments.save(commitment)
                    await self.uow.commit()
            else:
                commitment = Commitment(
                    owner_id=req.owner_id,
                    raw_text=req.raw_text,
                    source=req.source,
                    captured_at=ref_time,
                    idempotency_fingerprint=fingerprint,
                    interpretation_revision=1,
                )
                await self.uow.commitments.save(commitment)
                await self.uow.commit()

        expected_revision = commitment.interpretation_revision

        # Phase 2: Non-blocking extraction and proposal validation (zero write locks held)
        extracted = await self.extractor.extract(
            req.raw_text,
            reference_time=ref_time,
            user_timezone=req.user_timezone,
        )
        validated = self.validator.validate(
            extracted,
            reference_time=ref_time,
            user_timezone=req.user_timezone,
        )

        # Phase 3: Atomic aggregate assembly and revision verification
        async with self.uow:
            reloaded = await self.uow.commitments.get_for_owner(commitment.id, req.owner_id)
            if reloaded is None:
                raise EntityNotFoundError("Commitment", commitment.id)

            if reloaded.interpretation_revision != expected_revision:
                raise StaleInferenceError(
                    reloaded.id,
                    expected_revision,
                    reloaded.interpretation_revision,
                )

            if validated.clarification_needed:
                prompt = (
                    validated.clarification_prompt
                    or "Could you clarify the specific details of this commitment?"
                )
                reloaded.request_clarification(prompt)
                await self.uow.commitments.save(reloaded)
                await self.uow.commit()
                return IntakeOutcome(
                    status=IntakeStatus.AWAITING_CLARIFICATION,
                    commitment=reloaded,
                    clarification_prompt=prompt,
                )

            reloaded.record_interpretation(
                validated.title,
                {"priority": validated.priority.value},
            )
            await self.uow.commitments.save(reloaded)

            task = Task(
                owner_id=req.owner_id,
                title=validated.title,
                description=validated.description,
                priority=validated.priority,
                commitment_id=reloaded.id,
                due_date=validated.due_date,
                scheduled_date=validated.scheduled_date,
            )
            action = task.add_next_action(
                description=validated.next_action_description,
                tool_hint=validated.suggested_tool_hint,
                tool_args_hint=validated.suggested_tool_args,
            )

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

            return IntakeOutcome(
                status=IntakeStatus.CREATED,
                commitment=reloaded,
                task=task,
                next_action=action,
            )

    async def clarify(self, req: ClarificationRequest) -> IntakeOutcome:
        """Clarify an ambiguous commitment through the three-phase intake seam."""
        ref_time = req.reference_time or self.clock.now()
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=UTC)

        # Phase 1: Atomic identifier resolution, eligibility check, and revision increment
        async with self.uow:
            commitment = await self._resolve_commitment(req.commitment_id, req.owner_id)
            if commitment is None:
                raise EntityNotFoundError("Commitment", req.commitment_id)

            existing_task = await self.uow.tasks.find_by_commitment_id(commitment.id, req.owner_id)
            if existing_task is not None and existing_task.status == TaskStatus.COMPLETED:
                raise InvalidClarificationTargetError(
                    commitment.id,
                    "Associated task is already completed and cannot be clarified",
                )

            expected_revision = commitment.interpretation_revision + 1
            commitment.interpretation_revision = expected_revision
            commitment.interpretation_history.append(
                {
                    "clarification_submitted": req.clarification_response,
                    "recorded_at": self.clock.now().isoformat(),
                    "revision": expected_revision,
                }
            )
            await self.uow.commitments.save(commitment)
            await self.uow.commit()

        # Phase 2: Non-blocking model extraction with structured context
        combined_text = f"{commitment.raw_text}\nUser Clarification: {req.clarification_response}"
        extracted = await self.extractor.extract(
            combined_text,
            reference_time=ref_time,
            user_timezone=req.user_timezone,
        )
        validated = self.validator.validate(
            extracted,
            reference_time=ref_time,
            user_timezone=req.user_timezone,
        )

        # Phase 3: Atomic aggregate assembly and verification
        async with self.uow:
            reloaded = await self.uow.commitments.get_for_owner(commitment.id, req.owner_id)
            if reloaded is None:
                raise EntityNotFoundError("Commitment", commitment.id)

            if reloaded.interpretation_revision != expected_revision:
                raise StaleInferenceError(
                    reloaded.id,
                    expected_revision,
                    reloaded.interpretation_revision,
                )

            if validated.clarification_needed:
                prompt = validated.clarification_prompt or "Further clarification needed"
                reloaded.request_clarification(prompt)
                await self.uow.commitments.save(reloaded)
                await self.uow.commit()
                return IntakeOutcome(
                    status=IntakeStatus.AWAITING_CLARIFICATION,
                    commitment=reloaded,
                    clarification_prompt=prompt,
                )

            reloaded.record_interpretation(
                validated.title,
                {"clarification": req.clarification_response},
            )
            await self.uow.commitments.save(reloaded)

            existing_task = await self.uow.tasks.find_by_commitment_id(reloaded.id, req.owner_id)
            if existing_task is not None:
                existing_task.title = validated.title
                existing_task.description = validated.description
                existing_task.priority = validated.priority
                existing_task.due_date = validated.due_date
                existing_task.scheduled_date = validated.scheduled_date
                action = existing_task.get_current_next_action()
                if action is None:
                    action = existing_task.add_next_action(
                        description=validated.next_action_description,
                        tool_hint=validated.suggested_tool_hint,
                        tool_args_hint=validated.suggested_tool_args,
                    )
                task = existing_task
            else:
                task = Task(
                    owner_id=req.owner_id,
                    title=validated.title,
                    description=validated.description,
                    priority=validated.priority,
                    commitment_id=reloaded.id,
                    due_date=validated.due_date,
                    scheduled_date=validated.scheduled_date,
                )
                action = task.add_next_action(
                    description=validated.next_action_description,
                    tool_hint=validated.suggested_tool_hint,
                    tool_args_hint=validated.suggested_tool_args,
                )

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

            return IntakeOutcome(
                status=IntakeStatus.CREATED,
                commitment=reloaded,
                task=task,
                next_action=action,
            )

    async def _resolve_commitment(
        self,
        commitment_id: UUID | str,
        owner_id: str,
    ) -> Commitment | None:
        """Resolve commitment by UUID or short identifier within the owner scope."""
        if isinstance(commitment_id, UUID):
            return await self.uow.commitments.get_for_owner(commitment_id, owner_id)

        try:
            parsed_uuid = UUID(commitment_id)
            return await self.uow.commitments.get_for_owner(parsed_uuid, owner_id)
        except ValueError:
            pass

        clean_prefix = commitment_id.strip().lower().replace("-", "")
        if hasattr(self.uow.commitments, "find_by_id_prefix"):
            matches = await self.uow.commitments.find_by_id_prefix(clean_prefix, owner_id)
        else:
            all_c = await self.uow.commitments.list_by_owner(owner_id)
            matches = [
                c for c in all_c if str(c.id).replace("-", "").lower().startswith(clean_prefix)
            ]

        if not matches:
            return None
        if len(matches) > 1:
            raise AmbiguousIdentifierError(
                f"Identifier prefix '{commitment_id}' matches {len(matches)} commitments."
            )
        return matches[0]
