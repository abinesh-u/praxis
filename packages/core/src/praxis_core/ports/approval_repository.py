"""Approval repository port and in-memory test implementation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.common import ApprovalStatus


class ApprovalRepository(Protocol):
    """Abstract storage port for ApprovalRequest records."""

    async def get(self, approval_id: UUID) -> ApprovalRequest | None:
        """Retrieve approval request by ID."""
        ...

    async def get_for_owner(self, approval_id: UUID, owner_id: str) -> ApprovalRequest | None:
        """Retrieve approval request strictly enforcing owner boundary."""
        ...

    async def save(self, approval: ApprovalRequest) -> ApprovalRequest:
        """Persist or update approval request."""
        ...

    async def list_pending(self, owner_id: str) -> list[ApprovalRequest]:
        """List active pending approvals for an owner."""
        ...

    async def list_for_task(self, task_id: UUID, owner_id: str) -> list[ApprovalRequest]:
        """List approvals for one task within the owner boundary."""
        ...


class InMemoryApprovalRepository:
    """In-memory approval repository for testing."""

    def __init__(self) -> None:
        self._approvals: dict[UUID, ApprovalRequest] = {}

    async def get(self, approval_id: UUID) -> ApprovalRequest | None:
        req = self._approvals.get(approval_id)
        if req is None:
            return None
        return req.model_copy(deep=True)

    async def get_for_owner(self, approval_id: UUID, owner_id: str) -> ApprovalRequest | None:
        req = self._approvals.get(approval_id)
        if req is None or req.owner_id != owner_id:
            return None
        return req.model_copy(deep=True)

    async def save(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._approvals[approval.id] = approval.model_copy(deep=True)
        return approval

    async def list_pending(self, owner_id: str) -> list[ApprovalRequest]:
        return [
            a.model_copy(deep=True)
            for a in self._approvals.values()
            if a.owner_id == owner_id and a.status == ApprovalStatus.PENDING
        ]

    async def list_for_task(self, task_id: UUID, owner_id: str) -> list[ApprovalRequest]:
        return [
            a.model_copy(deep=True)
            for a in self._approvals.values()
            if a.owner_id == owner_id and a.task_id == task_id
        ]
