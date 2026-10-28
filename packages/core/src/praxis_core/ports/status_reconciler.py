"""StatusReconciler port defining the read-only inspection seam for uncertain executions."""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel

ReconcileStatus = Literal["completed", "failed", "outcome_unknown", "awaiting_approval"]


class RawReconcileResult(BaseModel):
    """Raw status check outcome from a remote provider."""

    status: ReconcileStatus
    provider_operation_id: str | None = None
    raw_payload: Any = None
    error: str | None = None
    failure_final: bool = False


class StatusReconciler(Protocol):
    """Read-only interface for querying the status of an uncertain remote operation."""

    async def inspect_status(
        self,
        attempt_id: UUID,
        idempotency_key: str,
        provider_operation_id: str | None,
    ) -> RawReconcileResult:
        """Inspect remote provider state without initiating execution or dispatch."""
        ...
