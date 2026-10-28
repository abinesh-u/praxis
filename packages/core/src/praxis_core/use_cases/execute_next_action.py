"""Use case for safely executing a task's immediate next action via bounded agent dispatcher."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus, DependencyType, TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.errors import (
    BlockedTaskError,
    EntityNotFoundError,
    InvalidStateTransitionError,
)
from praxis_core.execution.synthesizer import EvidenceSynthesizer
from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    RawDispatchResult,
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
    approval_token: str | None = None


class ExecuteNextActionResult(BaseModel):
    """Result of next action execution and reconciliation."""

    task: Task
    action: NextAction
    attempt: ExecutionAttempt | None = None
    outcome: AgentRunOutcome
    approval_request: ApprovalRequest | None = None
    approval_token: str | None = None


class ExecuteNextActionUseCase:
    """Orchestrates attempt persistence, dispatch execution, and outcome reconciliation."""

    def __init__(
        self,
        uow: UnitOfWork,
        dispatcher: ActionDispatcher | AgentRunner | None = None,
        clock: Clock | None = None,
        runner: ActionDispatcher | AgentRunner | None = None,
    ) -> None:
        self.uow = uow
        resolved = dispatcher or runner
        if resolved is None:
            raise ValueError("Either 'dispatcher' or 'runner' must be provided")
        self.dispatcher = resolved
        self.clock = clock or SystemClock()

    async def execute(self, cmd: ExecuteNextActionCommand) -> ExecuteNextActionResult:
        # Phase 1: Pre-execution risk assessment, authorization, and attempt persistence
        async with self.uow:
            task = await self.uow.tasks.get_for_owner(cmd.task_id, cmd.owner_id)
            if task is None:
                raise EntityNotFoundError("Task", cmd.task_id)

            action = task.get_current_next_action()
            if action is None and task.next_actions:
                action = task.next_actions[-1]
            elif action is None:
                action = task.add_next_action("Complete remaining task objectives")

            # Check idempotency first to safely replay completed, waiting, or running attempts
            existing_attempt = None
            if cmd.idempotency_key:
                existing_attempt = await self.uow.attempts.find_by_idempotency_key(
                    cmd.idempotency_key,
                    cmd.owner_id,
                )
            if existing_attempt is None and cmd.approval_token:
                task_attempts = await self.uow.attempts.list_for_task(task.id, cmd.owner_id)
                existing_attempt = next(
                    (
                        att
                        for att in reversed(task_attempts)
                        if att.action_id == action.id and att.status == "awaiting_approval"
                    ),
                    None,
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
                if existing_attempt.status == "awaiting_approval" and not cmd.approval_token:
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
                if existing_attempt.status == "outcome_unknown":
                    return ExecuteNextActionResult(
                        task=task,
                        action=matched_action,
                        attempt=existing_attempt,
                        outcome=AgentRunOutcome(
                            status="outcome_unknown",
                            error=existing_attempt.error
                            or "External outcome requires reconciliation before retry",
                            provider_request_id=existing_attempt.provider_request_id,
                        ),
                    )
                if existing_attempt.status == "running":
                    # Process crashed during in-flight execution; never blindly redispatch!
                    return ExecuteNextActionResult(
                        task=task,
                        action=matched_action,
                        attempt=existing_attempt,
                        outcome=AgentRunOutcome(
                            status="outcome_unknown",
                            error=(
                                "Execution attempt is in-flight or was interrupted; "
                                "reconcile provider state before retry"
                            ),
                            provider_request_id=existing_attempt.provider_request_id,
                        ),
                    )

            allowed_statuses = (TaskStatus.PLANNED, TaskStatus.IN_PROGRESS)
            if cmd.approval_token:
                allowed_statuses = (
                    TaskStatus.PLANNED,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.AWAITING_APPROVAL,
                )
            if task.status not in allowed_statuses:
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

            # Transition task to IN_PROGRESS if PLANNED
            if task.status == TaskStatus.PLANNED:
                task.start()

            # Pre-dispatch risk assessment
            requires_pre_dispatch_approval = action.risk_level in (
                ActionRiskLevel.CONSEQUENTIAL,
                ActionRiskLevel.DESTRUCTIVE,
            )

            idem_key = (
                cmd.idempotency_key or f"attempt_{task.id}_{action.id}_{action.execution_attempts}"
            )

            # If action requires approval and no token was supplied: halt before dispatch.
            # Record an awaiting_approval attempt rather than a misleading running attempt.
            if requires_pre_dispatch_approval and not cmd.approval_token:
                action_spec = ActionSpecification(
                    tool_name=action.tool_hint or "system_action",
                    canonical_args=action.tool_args_hint or {"target": action.description},
                    task_id=task.id,
                    permission_scope=(
                        "external_http" if action.tool_hint == "webhook_post" else "local_exec"
                    ),
                )
                approval_req, raw_token = ApprovalRequest.create(
                    owner_id=cmd.owner_id,
                    task_id=task.id,
                    action=action_spec,
                    risk_level=action.risk_level,
                    justification=f"Action '{action.description}' requires explicit authorization.",
                )
                attempt = ExecutionAttempt(
                    owner_id=cmd.owner_id,
                    task_id=task.id,
                    action_id=action.id,
                    idempotency_key=idem_key,
                    status="awaiting_approval",
                    approval_id=approval_req.id,
                )
                await self.uow.approvals.save(approval_req)
                await self.uow.attempts.save(attempt)
                task.await_approval(
                    reason=f"Action '{action.description}' requires explicit authorization."
                )
                self.uow.track_task(task)
                await self.uow.tasks.save(task)
                await self.uow.commit()

                return ExecuteNextActionResult(
                    task=task,
                    action=action,
                    attempt=attempt,
                    outcome=AgentRunOutcome(
                        status="awaiting_approval",
                        action_spec=action_spec,
                        approval_justification=(
                            f"Action '{action.description}' requires explicit authorization."
                        ),
                    ),
                    approval_request=approval_req,
                    approval_token=raw_token,
                )

            # If an approval token is supplied: atomically validate and consume it
            consumed_approval_id: UUID | None = None
            if cmd.approval_token:
                action_spec = ActionSpecification(
                    tool_name=action.tool_hint or "system_action",
                    canonical_args=action.tool_args_hint or {"target": action.description},
                    task_id=task.id,
                    permission_scope=(
                        "external_http" if action.tool_hint == "webhook_post" else "local_exec"
                    ),
                )
                approvals = await self.uow.approvals.list_for_task(task.id, cmd.owner_id)
                approval = next(
                    (
                        candidate
                        for candidate in approvals
                        if candidate.status == ApprovalStatus.APPROVED
                        and candidate.action_fingerprint == action_spec.fingerprint()
                    ),
                    None,
                )
                if approval is None:
                    # Match approved requests linked to pending attempts for this action
                    pending_approval_id = (
                        existing_attempt.approval_id
                        if existing_attempt and existing_attempt.status == "awaiting_approval"
                        else None
                    )
                    if pending_approval_id:
                        approval = await self.uow.approvals.get_for_owner(
                            pending_approval_id, cmd.owner_id
                        )
                        if approval and approval.status != ApprovalStatus.APPROVED:
                            approval = None
                    if approval is not None:
                        action_spec = approval.action

                if approval is None:
                    raise InvalidStateTransitionError(
                        task.status.value,
                        TaskStatus.IN_PROGRESS.value,
                        "No approved request matches this action",
                    )
                approval.consume(cmd.approval_token, action_spec)
                await self.uow.approvals.save(approval)
                consumed_approval_id = approval.id
                if task.status == TaskStatus.AWAITING_APPROVAL:
                    task.approval_granted()

            if existing_attempt is not None and existing_attempt.status == "awaiting_approval":
                attempt = existing_attempt
                attempt.status = "running"
                attempt.approval_id = consumed_approval_id
            else:
                attempt = ExecutionAttempt(
                    owner_id=cmd.owner_id,
                    task_id=task.id,
                    action_id=action.id,
                    idempotency_key=idem_key,
                    status="running",
                    approval_id=consumed_approval_id,
                )
                action.record_attempt()

            await self.uow.attempts.save(attempt)
            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

        # Phase 2: Dispatch execution outside atomic transaction
        dispatch_canonical_args = dict(action.tool_args_hint or {"description": action.description})
        if consumed_approval_id and approval is not None:
            dispatch_canonical_args["approved_tool"] = approval.action.tool_name
            dispatch_canonical_args["approved_args"] = approval.action.canonical_args

        dispatch_spec = DispatchSpec(
            attempt_id=attempt.id,
            idempotency_key=attempt.idempotency_key,
            tool_name=action.tool_hint or "system_action",
            canonical_args=dispatch_canonical_args,
            destination_context={
                "workspace_root": cmd.workspace_root,
                "owner_id": cmd.owner_id,
                "task_id": str(task.id),
                "action_id": str(action.id),
                "approval_token": cmd.approval_token,
                "approved": bool(consumed_approval_id),
            },
        )

        legacy_outcome: AgentRunOutcome | None = None
        if hasattr(self.dispatcher, "dispatch"):
            try:
                raw_result = await self.dispatcher.dispatch(dispatch_spec)
            except Exception as exc:
                raw_result = RawDispatchResult(
                    status="outcome_unknown",
                    error=f"Transport exception during dispatch: {exc}",
                )
        else:
            # Backward-compatibility fallback for legacy AgentRunner
            legacy_outcome = await self.dispatcher.execute_action(
                attempt_id=attempt.id,
                task=task,
                action=action,
                owner_id=cmd.owner_id,
                workspace_root=cmd.workspace_root,
                approval_token=cmd.approval_token,
            )
            if legacy_outcome.status == "awaiting_approval":
                async with self.uow:
                    task = await self.uow.tasks.get_for_owner(cmd.task_id, cmd.owner_id)
                    attempt = await self.uow.attempts.get_for_owner(attempt.id, cmd.owner_id)
                    action = next(
                        (a for a in task.next_actions if a.id == attempt.action_id),
                        task.get_current_next_action() or task.next_actions[-1],
                    )
                    action_spec = legacy_outcome.action_spec or ActionSpecification(
                        tool_name="unspecified_tool",
                        canonical_args={},
                        task_id=task.id,
                    )
                    approval_req, raw_token = ApprovalRequest.create(
                        owner_id=cmd.owner_id,
                        task_id=task.id,
                        action=action_spec,
                        risk_level=ActionRiskLevel.CONSEQUENTIAL,
                        justification=legacy_outcome.approval_justification
                        or "Tool requires approval",
                    )
                    await self.uow.approvals.save(approval_req)
                    attempt.mark_awaiting_approval(approval_req.id)
                    task.await_approval(reason=legacy_outcome.approval_justification or "")
                    self.uow.track_task(task)
                    await self.uow.tasks.save(task)
                    await self.uow.attempts.save(attempt)
                    await self.uow.commit()

                    return ExecuteNextActionResult(
                        task=task,
                        action=action,
                        attempt=attempt,
                        outcome=legacy_outcome,
                        approval_request=approval_req,
                        approval_token=raw_token,
                    )

            raw_result = RawDispatchResult(
                status=legacy_outcome.status,
                provider_operation_id=legacy_outcome.provider_request_id,
                raw_payload=legacy_outcome.output,
                error=legacy_outcome.error,
                failure_final=(legacy_outcome.status == "failed"),
            )

        # Phase 3: Post-execution reconciliation & Evidence Synthesis
        async with self.uow:
            task = await self.uow.tasks.get_for_owner(cmd.task_id, cmd.owner_id)
            attempt = await self.uow.attempts.get_for_owner(attempt.id, cmd.owner_id)
            action = next(
                (a for a in task.next_actions if a.id == attempt.action_id),
                task.get_current_next_action() or task.next_actions[-1],
            )

            if raw_result.status == "awaiting_approval":
                # Adapter halted for approval (e.g. interactive agent tool)
                raw_dict = (
                    raw_result.raw_payload if isinstance(raw_result.raw_payload, dict) else {}
                )
                spec = getattr(legacy_outcome, "action_spec", None) or ActionSpecification(
                    tool_name=raw_dict.get("tool_name") or action.tool_hint or "system_action",
                    canonical_args=(
                        raw_dict.get("tool_args")
                        or action.tool_args_hint
                        or {"target": action.description}
                    ),
                    task_id=task.id,
                    permission_scope=(
                        "external_http" if action.tool_hint == "webhook_post" else "local_exec"
                    ),
                )
                justification = (
                    raw_dict.get("justification")
                    or getattr(legacy_outcome, "approval_justification", None)
                    or f"Action '{action.description}' requires explicit authorization."
                )
                approval_req, raw_token = ApprovalRequest.create(
                    owner_id=cmd.owner_id,
                    task_id=task.id,
                    action=spec,
                    risk_level=ActionRiskLevel.CONSEQUENTIAL,
                    justification=justification,
                )
                attempt.mark_awaiting_approval(approval_req.id)
                task.await_approval(reason=justification)
                await self.uow.approvals.save(approval_req)
                self.uow.track_task(task)
                await self.uow.tasks.save(task)
                await self.uow.attempts.save(attempt)
                await self.uow.commit()

                return ExecuteNextActionResult(
                    task=task,
                    action=action,
                    attempt=attempt,
                    outcome=AgentRunOutcome(
                        status="awaiting_approval",
                        action_spec=spec,
                        approval_justification=justification,
                    ),
                    approval_request=approval_req,
                    approval_token=raw_token,
                )

            elif raw_result.status == "completed":
                # Evidence synthesis or legacy evidence pass-through
                legacy_evidence = getattr(legacy_outcome, "evidence", None)
                if legacy_evidence is not None:
                    evidence = legacy_evidence if legacy_evidence.is_verified() else None
                elif action.tool_hint == "webhook_post":
                    evidence = EvidenceSynthesizer.verify_and_synthesize_webhook_receipt(
                        task_id=task.id,
                        action_id=action.id,
                        attempt_id=attempt.id,
                        raw_result=raw_result,
                    )
                elif action.tool_hint in ("agent_runtime", "agent_loop") or (
                    isinstance(raw_result.raw_payload, dict) and "run_id" in raw_result.raw_payload
                ):
                    evidence = EvidenceSynthesizer.verify_and_synthesize_agent_receipt(
                        task_id=task.id,
                        action_id=action.id,
                        attempt_id=attempt.id,
                        raw_result=raw_result,
                    )
                else:
                    evidence = EvidenceSynthesizer.verify_and_synthesize_local_receipt(
                        task_id=task.id,
                        action_id=action.id,
                        attempt_id=attempt.id,
                        owner_id=cmd.owner_id,
                        action_description=action.description,
                        raw_result=raw_result,
                    )

                if evidence and evidence.is_verified():
                    action.mark_completed(evidence_id=evidence.id)
                    attempt.mark_completed(evidence_id=evidence.id)

                    remaining_actions = [a for a in task.next_actions if not a.completed]
                    if not remaining_actions and evidence.target_task_id == task.id:
                        task.complete(evidence=evidence)

                    normalized_outcome = AgentRunOutcome(
                        status="completed",
                        evidence=evidence,
                        output=raw_result.raw_payload,
                        provider_request_id=raw_result.provider_operation_id,
                    )
                else:
                    if legacy_evidence is not None and not legacy_evidence.is_verified():
                        # Direct test of agent asserting completed without verifiable evidence
                        err_msg = "Agent returned completed without verifiable evidence"
                        attempt.mark_failed(err_msg)
                        task.fail(
                            reason=err_msg,
                            recovery_suggestion="Verify action execution requirements and retry",
                        )
                        normalized_outcome = AgentRunOutcome(
                            status="failed",
                            error=err_msg,
                            output=raw_result.raw_payload,
                            provider_request_id=raw_result.provider_operation_id,
                        )
                    else:
                        # Ambiguous or unverified receipt from transport
                        err_msg = (
                            "Action completed without verifiable evidence; "
                            "reconcile before retrying"
                        )
                        attempt.mark_outcome_unknown(err_msg, raw_result.provider_operation_id)
                        task.recovery_suggestion = "Reconcile the provider outcome before retrying"
                        normalized_outcome = AgentRunOutcome(
                            status="outcome_unknown",
                            error=err_msg,
                            output=raw_result.raw_payload,
                            provider_request_id=raw_result.provider_operation_id,
                        )

            elif raw_result.status == "failed" and raw_result.failure_final:
                err_msg = raw_result.error or "Tool execution failed"
                attempt.mark_failed(err_msg)
                task.fail(
                    reason=err_msg,
                    recovery_suggestion="Review tool parameters or credentials and retry",
                )
                normalized_outcome = AgentRunOutcome(
                    status="failed",
                    error=err_msg,
                    output=raw_result.raw_payload,
                    provider_request_id=raw_result.provider_operation_id,
                )

            else:  # outcome_unknown or non-final failure
                err_msg = (
                    raw_result.error or "External outcome requires reconciliation before retry"
                )
                attempt.mark_outcome_unknown(
                    err_msg,
                    raw_result.provider_operation_id,
                )
                if raw_result.provider_operation_id:
                    task.recovery_suggestion = "Reconcile the provider outcome before retrying"
                else:
                    task.recovery_suggestion = (
                        "Provider operation ID is unavailable; inspect the provider manually "
                        "and do not retry until the outcome is established"
                    )
                normalized_outcome = AgentRunOutcome(
                    status="outcome_unknown",
                    error=err_msg,
                    provider_request_id=raw_result.provider_operation_id,
                    output=raw_result.raw_payload,
                )

            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.attempts.save(attempt)
            await self.uow.commit()

            return ExecuteNextActionResult(
                task=task,
                action=action,
                attempt=attempt,
                outcome=normalized_outcome,
                approval_request=None,
                approval_token=None,
            )
