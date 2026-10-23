"""Provider-independent reconciliation of uncertain execution attempts."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from praxis_core.errors import EntityNotFoundError, InvalidStateTransitionError
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome
from praxis_core.ports.unit_of_work import UnitOfWork
from praxis_core.use_cases.execute_next_action import ExecuteNextActionResult


class ReconcileExecutionCommand(BaseModel):
    task_id: UUID
    attempt_id: UUID
    owner_id: str


class ReconcileExecutionUseCase:
    """Resolve an existing attempt by observation; never calls the original action."""

    def __init__(self, uow: UnitOfWork, runner: AgentRunner) -> None:
        self.uow = uow
        self.runner = runner

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

        outcome = await self.runner.reconcile_action(
            attempt_id=attempt.id,
            task=task,
            action=action,
            owner_id=cmd.owner_id,
            provider_request_id=attempt.provider_request_id,
            idempotency_key=attempt.idempotency_key,
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
            if (
                outcome.status == "completed"
                and outcome.evidence
                and outcome.evidence.is_verified()
            ):
                action.mark_completed(evidence_id=outcome.evidence.id)
                attempt.mark_completed(evidence_id=outcome.evidence.id)
                if not [item for item in task.next_actions if not item.completed]:
                    task.complete(evidence=outcome.evidence)
            elif outcome.status == "outcome_unknown":
                attempt.mark_outcome_unknown(
                    outcome.error or "Provider still cannot confirm the outcome",
                    outcome.provider_request_id or attempt.provider_request_id,
                )
                task.recovery_suggestion = (
                    "Provider has not confirmed the outcome; reconcile again later"
                )
            else:
                attempt.mark_failed(outcome.error or "Provider reported execution failure")
                task.fail(
                    reason=outcome.error or "Provider reported execution failure",
                    recovery_suggestion="Review the provider result before taking further action",
                )
            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.attempts.save(attempt)
            await self.uow.commit()
            return ExecuteNextActionResult(
                task=task,
                action=action,
                attempt=attempt,
                outcome=outcome,
            )
