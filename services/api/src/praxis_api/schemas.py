"""Stable request and response schemas for the Praxis HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import (
    ActionRiskLevel,
    ApprovalStatus,
    Priority,
    SourceChannel,
    TaskStatus,
)
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.use_cases.capture_commitment import CaptureCommitmentResult
from praxis_core.use_cases.execute_next_action import ExecuteNextActionResult
from praxis_core.use_cases.get_daily_agenda import AgendaTaskItem, DailyAgendaResult
from praxis_core.use_cases.resolve_approval import ResolveApprovalResult
from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Reject unknown input fields so transport contracts remain explicit."""

    model_config = ConfigDict(extra="forbid")


class CaptureTaskRequest(ApiModel):
    owner_id: Annotated[str, Field(min_length=1, max_length=256)]
    raw_text: Annotated[str, Field(min_length=1, max_length=10_000)]
    source: SourceChannel = SourceChannel.API
    user_timezone: Annotated[str, Field(min_length=1, max_length=128)] = "UTC"
    idempotency_key: Annotated[str | None, Field(max_length=256)] = None
    reference_time: datetime | None = None


class ClarifyCommitmentRequest(ApiModel):
    owner_id: Annotated[str, Field(min_length=1, max_length=256)]
    clarification_response: Annotated[str, Field(min_length=1, max_length=10_000)]
    user_timezone: Annotated[str, Field(min_length=1, max_length=128)] = "UTC"
    reference_time: datetime | None = None


class CompleteTaskRequest(ApiModel):
    owner_id: Annotated[str, Field(min_length=1, max_length=256)]
    confirmation_note: Annotated[str, Field(min_length=1, max_length=4_000)]
    target_action_id: UUID | None = None


class ApprovalDecisionRequest(ApiModel):
    owner_id: Annotated[str, Field(min_length=1, max_length=256)]
    decision: Literal["approve", "reject"]
    rejection_reason: Annotated[str | None, Field(max_length=4_000)] = None
    fatal_rejection: bool = False


class ExecuteTaskRequest(ApiModel):
    owner_id: Annotated[str, Field(min_length=1, max_length=256)]
    idempotency_key: Annotated[str, Field(min_length=1, max_length=256)]
    approval_token: Annotated[str | None, Field(max_length=512)] = None
    workspace_root: Annotated[str | None, Field(max_length=1_000)] = None
    attempt_id: UUID | None = None


class ReconcileTaskRequest(ApiModel):
    owner_id: Annotated[str, Field(min_length=1, max_length=256)]
    attempt_id: UUID


class ExecutionResponse(ApiModel):
    task: TaskResponse
    attempt_id: UUID | None = None
    attempt_status: str | None = None
    outcome_status: str
    output: Any = None
    error: str | None = None
    provider_request_id: str | None = None
    approval: ApprovalResponse | None = None
    approval_token: str | None = None

    @classmethod
    def from_result(cls, result: ExecuteNextActionResult) -> ExecutionResponse:
        return cls(
            task=TaskResponse.from_entity(result.task, result.action),
            attempt_id=result.attempt.id if result.attempt else None,
            attempt_status=result.attempt.status if result.attempt else None,
            outcome_status=result.outcome.status,
            output=result.outcome.output,
            error=result.outcome.error,
            provider_request_id=(
                (result.attempt.provider_request_id if result.attempt else None)
                or result.outcome.provider_request_id
            ),
            approval=ApprovalResponse.from_entity(result.approval_request)
            if result.approval_request
            else None,
            approval_token=result.approval_token,
        )


class NextActionResponse(ApiModel):
    id: UUID
    task_id: UUID
    description: str
    tool_hint: str | None
    tool_args_hint: dict[str, Any] | None
    risk_level: ActionRiskLevel
    completed: bool
    completed_at: datetime | None
    evidence_id: UUID | None
    sort_order: int
    execution_attempts: int

    @classmethod
    def from_entity(cls, action: NextAction | None) -> NextActionResponse | None:
        if action is None:
            return None
        return cls(
            id=action.id,
            task_id=action.task_id,
            description=action.description,
            tool_hint=action.tool_hint,
            tool_args_hint=action.tool_args_hint,
            risk_level=action.risk_level,
            completed=action.completed,
            completed_at=action.completed_at,
            evidence_id=action.evidence_id,
            sort_order=action.sort_order,
            execution_attempts=action.execution_attempts,
        )


class TaskResponse(ApiModel):
    id: UUID
    owner_id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    due_date: datetime | None
    scheduled_date: datetime | None
    completed_at: datetime | None
    deferred_until: datetime | None
    failure_reason: str | None
    recovery_suggestion: str | None
    current_next_action: NextActionResponse | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, task: Task, current_next_action: NextAction | None = None) -> TaskResponse:
        return cls(
            id=task.id,
            owner_id=task.owner_id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            scheduled_date=task.scheduled_date,
            completed_at=task.completed_at,
            deferred_until=task.deferred_until,
            failure_reason=task.failure_reason,
            recovery_suggestion=task.recovery_suggestion,
            current_next_action=NextActionResponse.from_entity(
                current_next_action or task.get_current_next_action()
            ),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class CommitmentResponse(ApiModel):
    id: UUID
    owner_id: str
    raw_text: str
    source: SourceChannel
    captured_at: datetime
    interpreted_intent: str | None
    clarification_needed: bool
    clarification_prompt: str | None

    @classmethod
    def from_entity(cls, commitment: Commitment) -> CommitmentResponse:
        return cls(
            id=commitment.id,
            owner_id=commitment.owner_id,
            raw_text=commitment.raw_text,
            source=commitment.source,
            captured_at=commitment.captured_at,
            interpreted_intent=commitment.interpreted_intent,
            clarification_needed=commitment.clarification_needed,
            clarification_prompt=commitment.clarification_prompt,
        )


class CaptureTaskResponse(ApiModel):
    commitment: CommitmentResponse
    task: TaskResponse | None
    clarification_needed: bool
    clarification_prompt: str | None

    @classmethod
    def from_result(cls, result: CaptureCommitmentResult) -> CaptureTaskResponse:
        return cls(
            commitment=CommitmentResponse.from_entity(result.commitment),
            task=(
                TaskResponse.from_entity(result.task, result.next_action)
                if result.task is not None
                else None
            ),
            clarification_needed=result.clarification_needed,
            clarification_prompt=result.clarification_prompt,
        )


class TaskListResponse(ApiModel):
    tasks: list[TaskResponse]
    limit: int = 100
    offset: int = 0
    has_more: bool = False


class AgendaItemResponse(ApiModel):
    task: TaskResponse
    is_blocked: bool
    waiting_reason: str | None
    attempt: AttemptSummaryResponse | None = None

    @classmethod
    def from_item(
        cls,
        item: AgendaTaskItem,
        attempts: list[ExecutionAttempt] | None = None,
    ) -> AgendaItemResponse:
        latest = attempts[0] if attempts else None
        return cls(
            task=TaskResponse.from_entity(item.task, item.current_next_action),
            is_blocked=item.is_blocked,
            waiting_reason=item.waiting_reason,
            attempt=AttemptSummaryResponse.from_entity(latest) if latest else None,
        )


class AttemptSummaryResponse(ApiModel):
    """Safe, bounded execution metadata for agenda views."""

    id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    provider_request_id: str | None
    evidence_id: UUID | None
    error: str | None

    @classmethod
    def from_entity(cls, attempt: ExecutionAttempt) -> AttemptSummaryResponse:
        return cls(
            id=attempt.id,
            status=attempt.status,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            provider_request_id=attempt.provider_request_id,
            evidence_id=attempt.evidence_id,
            error=attempt.error,
        )


class TodayResponse(ApiModel):
    date: datetime
    actionable: list[AgendaItemResponse]
    waiting: list[AgendaItemResponse]

    @classmethod
    def from_result(cls, result: DailyAgendaResult) -> TodayResponse:
        return cls.from_result_with_attempts(result, {})

    @classmethod
    def from_result_with_attempts(
        cls,
        result: DailyAgendaResult,
        attempts_by_task: dict[UUID, list[ExecutionAttempt]],
    ) -> TodayResponse:
        return cls(
            date=result.date,
            actionable=[
                AgendaItemResponse.from_item(item, attempts_by_task.get(item.task.id, []))
                for item in result.actionable
            ],
            waiting=[
                AgendaItemResponse.from_item(item, attempts_by_task.get(item.task.id, []))
                for item in result.waiting
            ],
        )


class ApprovalResponse(ApiModel):
    id: UUID
    task_id: UUID
    tool_name: str
    canonical_args: dict[str, Any]
    risk_level: ActionRiskLevel
    justification: str
    status: ApprovalStatus
    expires_at: datetime
    decided_at: datetime | None
    rejection_reason: str | None

    @classmethod
    def from_entity(cls, approval: ApprovalRequest) -> ApprovalResponse:
        return cls(
            id=approval.id,
            task_id=approval.task_id,
            tool_name=approval.action.tool_name,
            canonical_args=approval.action.canonical_args,
            risk_level=approval.risk_level,
            justification=approval.justification,
            status=approval.status,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
            rejection_reason=approval.rejection_reason,
        )


class ApprovalListResponse(ApiModel):
    approvals: list[ApprovalResponse]


class ApprovalDecisionResponse(ApiModel):
    approval: ApprovalResponse
    task: TaskResponse

    @classmethod
    def from_result(cls, result: ResolveApprovalResult) -> ApprovalDecisionResponse:
        return cls(
            approval=ApprovalResponse.from_entity(result.approval),
            task=TaskResponse.from_entity(result.task),
        )
