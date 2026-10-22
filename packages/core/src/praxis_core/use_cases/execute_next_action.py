"""Use case for safely executing a task's immediate next action via bounded agent runner."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, DependencyType, TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.errors import (
    BlockedTaskError,
    EntityNotFoundError,
    InvalidStateTransitionError,
)
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome
from praxis_core.ports.clock import Clock, SystemClock
from praxis_core.ports.unit_of_work import UnitOfWork


class ExecuteNextActionCommand(BaseModel):
    """Command input for executing a task's next action."""

    task_id: UUID
    owner_id: str
    workspace_root: str | None = None
    idempotency_key: str | None = None


class ExecuteNextActionResult(BaseModel):
    """Result of next action execution and reconciliation."""

    task: Task
    action: NextAction
    attempt: ExecutionAttempt
    outcome: AgentRunOutcome
    approval_request: ApprovalRequest | None = None


class ExecuteNextActionUseCase:
    """Orchestrates attempt persistence, runner execution, and outcome reconciliation."""

    def __init__(
        self,
        uow: UnitOfWork,
        runner: AgentRunner,
        clock: Clock | None = None,
    ) -> None:
        self.uow = uow
        self.runner = runner
        self.clock = clock or SystemClock()

    async def execute(self, cmd: ExecuteNextActionCommand) -> ExecuteNextActionResult:
        # Phase 1: Pre-execution validation & attempt persistence
        async with self.uow:
            task = await self.uow.tasks.get_for_owner(cmd.task_id, cmd.owner_id)
            if task is None:
                raise EntityNotFoundError("Task", cmd.task_id)

            action = task.get_current_next_action()
            if action is None and task.next_actions:
                action = task.next_actions[-1]
            elif action is None:
                action = task.add_next_action("Complete remaining task objectives")

            # Check idempotency first to safely replay completed or waiting attempts
            if cmd.idempotency_key:
                existing_attempt = await self.uow.attempts.find_by_idempotency_key(
                    cmd.idempotency_key,
                    cmd.owner_id,
                )
                if existing_attempt is not None:
                    matched_action = next(
                        (a for a in task.next_actions if a.id == existing_attempt.action_id),
                        action,
                    )
                    if existing_attempt.status == "completed":
                        return ExecuteNextActionResult(
                            task=task,
                            action=matched_action,
                            attempt=existing_attempt,
                            outcome=AgentRunOutcome(
                                status="completed",
                                output="Action already completed (idempotent replay)",
                            ),
                        )
                    if existing_attempt.status == "awaiting_approval":
                        approval = None
                        if existing_attempt.approval_id:
                            approval = await self.uow.approvals.get_for_owner(
                                existing_attempt.approval_id,
                                cmd.owner_id,
                            )
                        return ExecuteNextActionResult(
                            task=task,
                            action=matched_action,
                            attempt=existing_attempt,
                            outcome=AgentRunOutcome(status="awaiting_approval"),
                            approval_request=approval,
                        )

            if task.status not in (TaskStatus.PLANNED, TaskStatus.IN_PROGRESS):
                raise InvalidStateTransitionError(
                    task.status.value,
                    TaskStatus.IN_PROGRESS.value,
                    f"Cannot execute next action when task is in '{task.status.value}' status",
                )

            # Check blockers
            blocking_ids: list[UUID] = []
            for dep in task.dependencies:
                if dep.dependency_type == DependencyType.BLOCKS:
                    prereq = await self.uow.tasks.get_for_owner(
                        dep.depends_on_task_id,
                        cmd.owner_id,
                    )
                    if prereq is None or prereq.status != TaskStatus.COMPLETED:
                        blocking_ids.append(dep.depends_on_task_id)

            if blocking_ids:
                raise BlockedTaskError(task.id, blocking_ids)

            if task.status == TaskStatus.PLANNED:
                task.start()

            idem_key = (
                cmd.idempotency_key or f"attempt_{task.id}_{action.id}_{action.execution_attempts}"
            )
            attempt = ExecutionAttempt(
                owner_id=cmd.owner_id,
                task_id=task.id,
                action_id=action.id,
                idempotency_key=idem_key,
                status="running",
            )
            action.record_attempt()

            await self.uow.attempts.save(attempt)
            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

        # Phase 2: Tool execution via AgentRunner (outside atomic transaction)
        outcome = await self.runner.execute_action(
            attempt_id=attempt.id,
            task=task,
            action=action,
            owner_id=cmd.owner_id,
            workspace_root=cmd.workspace_root,
        )

        # Phase 3: Post-execution reconciliation
        approval_req: ApprovalRequest | None = None
        async with self.uow:
            task = await self.uow.tasks.get_for_owner(cmd.task_id, cmd.owner_id)
            attempt = await self.uow.attempts.get_for_owner(attempt.id, cmd.owner_id)
            action = next(
                (a for a in task.next_actions if a.id == attempt.action_id),
                task.get_current_next_action() or task.next_actions[-1],
            )

            if outcome.status == "awaiting_approval":
                action_spec = outcome.action_spec or ActionSpecification(
                    tool_name="unspecified_tool",
                    canonical_args={},
                    task_id=task.id,
                )
                approval_req, _ = ApprovalRequest.create(
                    owner_id=cmd.owner_id,
                    task_id=task.id,
                    action=action_spec,
                    risk_level=ActionRiskLevel.CONSEQUENTIAL,
                    justification=outcome.approval_justification or "Tool requires approval",
                )
                await self.uow.approvals.save(approval_req)
                attempt.mark_awaiting_approval(approval_req.id)
                task.await_approval(reason=outcome.approval_justification or "")

            elif outcome.status == "completed":
                if outcome.evidence and outcome.evidence.is_verified():
                    action.mark_completed(evidence_id=outcome.evidence.id)
                    attempt.mark_completed(evidence_id=outcome.evidence.id)

                    # Complete task only if all next actions are completed
                    remaining_actions = [a for a in task.next_actions if not a.completed]
                    if not remaining_actions and outcome.evidence.target_task_id == task.id:
                        task.complete(evidence=outcome.evidence)
                else:
                    attempt.mark_failed("Agent returned completed without verifiable evidence")
                    task.fail(
                        reason="Agent returned completed without verifiable evidence",
                        recovery_suggestion="Verify action execution requirements and retry",
                    )

            else:  # failed
                err_msg = outcome.error or "Tool execution failed"
                attempt.mark_failed(err_msg)
                task.fail(
                    reason=err_msg,
                    recovery_suggestion="Review tool parameters or credentials and retry",
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
                approval_request=approval_req,
            )
