"""Commitment repository port and in-memory test implementation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from praxis_core.entities.commitment import Commitment


class CommitmentRepository(Protocol):
    """Abstract storage port for Commitment records."""

    async def get(self, commitment_id: UUID) -> Commitment | None:
        """Retrieve commitment by ID."""
        ...

    async def get_for_owner(self, commitment_id: UUID, owner_id: str) -> Commitment | None:
        """Retrieve commitment strictly enforcing owner boundary."""
        ...

    async def save(self, commitment: Commitment) -> Commitment:
        """Persist or update commitment."""
        ...

    async def list_by_owner(self, owner_id: str) -> list[Commitment]:
        """List all commitments for an owner."""
        ...

    async def find_by_idempotency_key(
        self,
        key: str,
        owner_id: str,
    ) -> Commitment | None:
        """Find commitment by idempotency key and owner."""
        ...


class InMemoryCommitmentRepository:
    """In-memory commitment repository for testing."""

    def __init__(self) -> None:
        self._commitments: dict[UUID, Commitment] = {}

    async def get(self, commitment_id: UUID) -> Commitment | None:
        c = self._commitments.get(commitment_id)
        if c is None:
            return None
        return c.model_copy(deep=True)

    async def get_for_owner(self, commitment_id: UUID, owner_id: str) -> Commitment | None:
        c = self._commitments.get(commitment_id)
        if c is None or c.owner_id != owner_id:
            return None
        return c.model_copy(deep=True)

    async def save(self, commitment: Commitment) -> Commitment:
        self._commitments[commitment.id] = commitment.model_copy(deep=True)
        return commitment

    async def list_by_owner(self, owner_id: str) -> list[Commitment]:
        return [
            c.model_copy(deep=True) for c in self._commitments.values() if c.owner_id == owner_id
        ]

    async def find_by_idempotency_key(
        self,
        key: str,
        owner_id: str,
    ) -> Commitment | None:
        for c in self._commitments.values():
            if c.owner_id == owner_id and c.idempotency_key == key:
                return c.model_copy(deep=True)
        return None
