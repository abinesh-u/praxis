"""Audit sink port and in-memory test implementation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from praxis_core.events import DomainEvent


class AuditSink(Protocol):
    """Abstract port for persisting domain audit events."""

    async def record(self, event: DomainEvent) -> None:
        """Persist a single domain event."""
        ...

    async def record_all(self, events: list[DomainEvent]) -> None:
        """Persist a batch of domain events."""
        ...


class InMemoryAuditSink:
    """In-memory audit sink storing events in an append-only log."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    async def record(self, event: DomainEvent) -> None:
        self._events.append(event)

    async def record_all(self, events: list[DomainEvent]) -> None:
        self._events.extend(events)

    def get_events(self, aggregate_id: UUID | None = None) -> list[DomainEvent]:
        """Query recorded events, optionally filtered by aggregate ID."""
        if aggregate_id is None:
            return list(self._events)
        return [e for e in self._events if e.aggregate_id == aggregate_id]

    def clear(self) -> None:
        """Clear recorded events."""
        self._events.clear()
