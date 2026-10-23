"""Dependency injection and service container wiring for Praxis CLI."""

from __future__ import annotations

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.task import Task
from praxis_core.errors import DomainError, EntityNotFoundError
from praxis_core.models.extractor import NebiusTaskExtractor
from praxis_core.ports.agent_runner import AgentRunner
from praxis_core.ports.clock import SystemClock
from praxis_core.ports.task_extractor import TaskExtractor
from praxis_core.ports.unit_of_work import UnitOfWork
from praxis_core.use_cases import (
    CaptureCommitmentUseCase,
    ClarifyCommitmentUseCase,
    CompleteTaskUseCase,
    DeferTaskUseCase,
    ExecuteNextActionUseCase,
    GetDailyAgendaUseCase,
    ResolveApprovalUseCase,
)

from praxis_cli.config import CliConfig
from praxis_cli.store import JsonFileUnitOfWork


class AmbiguousIdentifierError(DomainError):
    """Raised when a short ID prefix matches more than one entity."""


def get_uow(config: CliConfig) -> JsonFileUnitOfWork:
    """Build a JsonFileUnitOfWork for the resolved profile storage path."""
    return JsonFileUnitOfWork(store_path=config.store_path)


def get_task_extractor() -> TaskExtractor:
    """Build task extractor backed by Nebius with graceful deterministic fallback."""
    return NebiusTaskExtractor()


def make_capture_use_case(config: CliConfig) -> CaptureCommitmentUseCase:
    return CaptureCommitmentUseCase(
        uow=get_uow(config),
        extractor=get_task_extractor(),
        clock=SystemClock(),
    )


def make_clarify_use_case(config: CliConfig) -> ClarifyCommitmentUseCase:
    return ClarifyCommitmentUseCase(
        uow=get_uow(config),
        extractor=get_task_extractor(),
        clock=SystemClock(),
    )


def make_agenda_use_case(config: CliConfig) -> GetDailyAgendaUseCase:
    return GetDailyAgendaUseCase(
        uow=get_uow(config),
        clock=SystemClock(),
    )


def make_complete_use_case(config: CliConfig) -> CompleteTaskUseCase:
    return CompleteTaskUseCase(uow=get_uow(config))


def make_defer_use_case(config: CliConfig) -> DeferTaskUseCase:
    return DeferTaskUseCase(uow=get_uow(config))


def make_resolve_approval_use_case(config: CliConfig) -> ResolveApprovalUseCase:
    return ResolveApprovalUseCase(uow=get_uow(config))


def make_execute_next_action_use_case(
    config: CliConfig, runner: AgentRunner
) -> ExecuteNextActionUseCase:
    return ExecuteNextActionUseCase(
        uow=get_uow(config),
        runner=runner,
        clock=SystemClock(),
    )


async def resolve_task_by_short_id(uow: UnitOfWork, short_id: str, owner_id: str) -> Task:
    """Resolve an 8-character prefix strictly within the active owner boundary."""
    clean_prefix = short_id.strip().lower().replace("-", "")
    all_tasks = await uow.tasks.list_by_owner(owner_id)
    matches = [t for t in all_tasks if str(t.id).replace("-", "").lower().startswith(clean_prefix)]
    if not matches:
        raise EntityNotFoundError("Task", short_id)
    if len(matches) > 1:
        raise AmbiguousIdentifierError(
            f"Short ID '{short_id}' matches {len(matches)} tasks. Provide more characters."
        )
    return matches[0]


async def resolve_commitment_by_short_id(
    uow: UnitOfWork, short_id: str, owner_id: str
) -> Commitment:
    """Resolve an 8-character prefix for commitments strictly within the active owner boundary."""
    clean_prefix = short_id.strip().lower().replace("-", "")
    # Find matching commitment across owner records
    if hasattr(uow.commitments, "_commitments"):
        matches = [
            Commitment.model_validate(raw)
            for raw in uow.commitments._commitments.values()
            if raw.get("owner_id") == owner_id
            and str(raw.get("id", "")).replace("-", "").lower().startswith(clean_prefix)
        ]
        if not matches:
            raise EntityNotFoundError("Commitment", short_id)
        if len(matches) > 1:
            raise AmbiguousIdentifierError(
                f"Short ID '{short_id}' matches {len(matches)} commitments."
            )
        return matches[0]
    raise EntityNotFoundError("Commitment", short_id)


async def resolve_approval_by_short_id(
    uow: UnitOfWork, short_id: str, owner_id: str
) -> ApprovalRequest:
    """Resolve an 8-character prefix for approvals strictly within the active owner boundary."""
    clean_prefix = short_id.strip().lower().replace("-", "")
    pending = await uow.approvals.list_pending(owner_id)
    matches = [a for a in pending if str(a.id).replace("-", "").lower().startswith(clean_prefix)]
    if not matches:
        raise EntityNotFoundError("ApprovalRequest", short_id)
    if len(matches) > 1:
        raise AmbiguousIdentifierError(
            f"Short ID '{short_id}' matches {len(matches)} approval requests."
        )
    return matches[0]
