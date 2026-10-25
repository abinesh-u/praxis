"""ActionDispatcher port defining the narrow execution seam between core and transport adapters."""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

DispatchStatus = Literal["completed", "failed", "outcome_unknown"]


class DispatchSpec(BaseModel):
    """Immutable specification passed across the dispatch seam to transport adapters."""

    attempt_id: UUID
    idempotency_key: str
    tool_name: str
    canonical_args: dict[str, Any] = Field(default_factory=dict)
    destination_context: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class RawDispatchResult(BaseModel):
    """Raw transport outcome returned by an adapter without self-certified evidence."""

    status: DispatchStatus
    provider_operation_id: str | None = None
    raw_payload: Any = None
    error: str | None = None
    failure_final: bool = False


class ActionDispatcher(Protocol):
    """Narrow execution interface implemented by environmental transport adapters."""

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        """Dispatch an authorized action specification through the environmental transport."""
        ...
