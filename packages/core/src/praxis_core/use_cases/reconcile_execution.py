"""Provider-independent reconciliation of uncertain execution attempts."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import TaskStatus
from praxis_core.errors import EntityNotFoundError, InvalidStateTransitionError
from praxis_core.execution.synthesizer import EvidenceSynthesizer
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome
from praxis_core.ports.status_reconciler import RawReconcileResult, StatusReconciler
from praxis_core.ports.unit_of_work import UnitOfWork
from praxis_core.use_cases.execute_next_action import ExecuteNextActionResult


class ReconcileExecutionCommand(BaseModel):
    task_id: UUID
    attempt_id: UUID
    owner_id: str


class ReconcileExecutionUseCase:
    """Resolve an existing attempt by observation; never calls the original action."""

    def __init__(
        self,
        uow: UnitOfWork,
        reconciler: StatusReconciler | AgentRunner | None = None,
        runner: StatusReconciler | AgentRunner | None = None,
    ) -> None:
        self.uow = uow
        resolved = reconciler or runner
        if resolved is None:
            raise ValueError("Either 'reconciler' or 'runner' must be provided")
        self.reconciler = resolved

    async def execute(self, cmd: ReconcileExecutionCommand) -> ExecuteNextActionResult:
        async with self.uow:
            attempt = await self.uow.attempts.get_for_owner(cmd.attempt_id, cmd.owner_id)
            if attempt is None:
                raise EntityNotFoundError("ExecutionAttempt", cmd.attempt_id)
            if attempt.task_id != cmd.task_id:
                raise InvalidStateTransitionError(
                    "attempt_task_mismatch",
                    "matching_task",
                    "Execution attempt does not belong to the requested task",
                )
            task = await self.uow.tasks.get_for_owner(attempt.task_id, cmd.owner_id)
            if task is None:
                raise EntityNotFoundError("Task", attempt.task_id)
            action = next(
                (item for item in task.next_actions if item.id == attempt.action_id), None
            )
            if action is None:
                raise EntityNotFoundError("NextAction", attempt.action_id)
            if attempt.status != "outcome_unknown":
                raise InvalidStateTransitionError(
                    attempt.status,
                    "outcome_unknown",
                    "Only uncertain execution attempts can be reconciled",
                )

        legacy_outcome: AgentRunOutcome | None = None
        if hasattr(self.reconciler, "inspect_status"):
            raw_reconcile = await self.reconciler.inspect_status(
                attempt_id=attempt.id,
                idempotency_key=attempt.idempotency_key,
                provider_operation_id=attempt.provider_request_id,
            )
        else:
            # Fallback for legacy AgentRunner
            legacy_outcome = await self.reconciler.reconcile_action(
                attempt_id=attempt.id,
                task=task,
                action=action,
                owner_id=cmd.owner_id,
                provider_request_id=attempt.provider_request_id,
                idempotency_key=attempt.idempotency_key,
            )
            raw_reconcile = RawReconcileResult(
                status=legacy_outcome.status,
                provider_operation_id=legacy_outcome.provider_request_id,
                raw_payload=legacy_outcome.output,
                error=legacy_outcome.error,
                failure_final=(legacy_outcome.status == "failed"),
            )

        async with self.uow:
            task = await self.uow.tasks.get_for_owner(attempt.task_id, cmd.owner_id)
            attempt = await self.uow.attempts.get_for_owner(attempt.id, cmd.owner_id)
            action = next(item for item in task.next_actions if item.id == attempt.action_id)
            if attempt.status != "outcome_unknown":
                terminal_status = "completed" if attempt.status == "completed" else "failed"
                return ExecuteNextActionResult(
                    task=task,
                    action=action,
                    attempt=attempt,
                    outcome=AgentRunOutcome(
                        status=terminal_status,
                        output="Attempt was reconciled by another request",
                    ),
                )

            if raw_reconcile.status == "completed":
                if (
                    legacy_outcome is not None
                    and legacy_outcome.evidence
                    and legacy_outcome.evidence.is_verified()
                ):
                    evidence: Evidence | None = legacy_outcome.evidence
                elif action.tool_hint == "webhook_post":
                    evidence = EvidenceSynthesizer.verify_and_synthesize_webhook_receipt(
                        task_id=task.id,
                        action_id=action.id,
                        attempt_id=attempt.id,
                        raw_result=raw_reconcile,
                    )
                elif action.tool_hint in ("agent_runtime", "agent_loop") or (
                    isinstance(raw_reconcile.raw_payload, dict)
                    and "run_id" in raw_reconcile.raw_payload
                ):
                    evidence = EvidenceSynthesizer.verify_and_synthesize_agent_receipt(
                        task_id=task.id,
                        action_id=action.id,
                        attempt_id=attempt.id,
                        raw_result=raw_reconcile,
                    )
                else:
                    evidence = EvidenceSynthesizer.verify_and_synthesize_webhook_receipt(
                        task_id=task.id,
                        action_id=action.id,
                        attempt_id=attempt.id,
                        raw_result=raw_reconcile,
                    )

                if evidence and evidence.is_verified():
                    action.mark_completed(evidence_id=evidence.id)
                    attempt.mark_completed(evidence_id=evidence.id)
                    if task.status == TaskStatus.PLANNED:
                        task.start()
                    elif task.status == TaskStatus.AWAITING_APPROVAL:
                        task.approval_granted()
                    remaining = [item for item in task.next_actions if not item.completed]
                    if not remaining:
                        task.complete(evidence=evidence)
                    norm_outcome = AgentRunOutcome(
                        status="completed",
                        evidence=evidence,
                        output=raw_reconcile.raw_payload,
                        provider_request_id=raw_reconcile.provider_operation_id,
                    )
                else:
                    attempt.mark_outcome_unknown(
                        "Reconciliation returned unverified completion; reconcile again later",
                        raw_reconcile.provider_operation_id or attempt.provider_request_id,
                    )
                    task.recovery_suggestion = (
                        "Provider outcome remains uncertain; reconcile again later"
                    )
                    norm_outcome = AgentRunOutcome(
                        status="outcome_unknown",
                        error=(
                            "Reconciliation returned unverified completion; reconcile again later"
                        ),
                        provider_request_id=raw_reconcile.provider_operation_id
                        or attempt.provider_request_id,
                    )

            elif raw_reconcile.status == "failed" and raw_reconcile.failure_final:
                err_msg = raw_reconcile.error or "Provider reported execution failure"
                attempt.mark_failed(err_msg)
                if task.status == TaskStatus.PLANNED:
                    task.start()
                task.fail(
                    reason=err_msg,
                    recovery_suggestion="Review the provider result before taking further action",
                )
                norm_outcome = AgentRunOutcome(
                    status="failed",
                    error=err_msg,
                    provider_request_id=raw_reconcile.provider_operation_id,
                )

            else:  # outcome_unknown or non-final failure
                attempt.mark_outcome_unknown(
                    raw_reconcile.error or "Provider still cannot confirm the outcome",
                    raw_reconcile.provider_operation_id or attempt.provider_request_id,
                )
                task.recovery_suggestion = (
                    "Provider has not confirmed the outcome; reconcile again later"
                )
                norm_outcome = AgentRunOutcome(
                    status="outcome_unknown",
                    error=raw_reconcile.error or "Provider still cannot confirm the outcome",
                    provider_request_id=raw_reconcile.provider_operation_id
                    or attempt.provider_request_id,
                )

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.attempts.save(attempt)
            await self.uow.commit()

            return ExecuteNextActionResult(
                task=task,
                action=action,
                attempt=attempt,
                outcome=norm_outcome,
            )
