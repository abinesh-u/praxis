"""Use case for deciding on pending consequential action approvals."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError
from praxis_core.ports.unit_of_work import UnitOfWork


class ResolveApprovalCommand(BaseModel):
    """Command input for resolving an approval request."""

    approval_id: UUID
    owner_id: str
    decision: str  # "approve" | "reject"
    rejection_reason: str | None = None
    fatal_rejection: bool = False


class ResolveApprovalResult(BaseModel):
    """Result of approval resolution."""

    approval: ApprovalRequest
    task: Task


class ResolveApprovalUseCase:
    """Safely approves or rejects a pending tool execution approval."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, cmd: ResolveApprovalCommand) -> ResolveApprovalResult:
        async with self.uow:
            approval = await self.uow.approvals.get_for_owner(
                cmd.approval_id,
                cmd.owner_id,
            )
            if approval is None:
                raise EntityNotFoundError("ApprovalRequest", cmd.approval_id)

            task = await self.uow.tasks.get_for_owner(
                approval.task_id,
                cmd.owner_id,
            )
            if task is None:
                raise EntityNotFoundError("Task", approval.task_id)

            norm_decision = cmd.decision.strip().lower()
            if norm_decision == "approve":
                approval.approve(decided_by=cmd.owner_id)
                task.approval_granted()
            elif norm_decision == "reject":
                reason = cmd.rejection_reason or "Action rejected by user"
                approval.reject(decided_by=cmd.owner_id, reason=reason)
                task.approval_rejected(fatal=cmd.fatal_rejection, reason=reason)
            else:
                raise ValueError(
                    f"Invalid decision '{cmd.decision}'. Must be 'approve' or 'reject'."
                )

            await self.uow.approvals.save(approval)
            self.uow.track_task(task)
            await self.uow.tasks.save(task)
            await self.uow.commit()

            return ResolveApprovalResult(approval=approval, task=task)
