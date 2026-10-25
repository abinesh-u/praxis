"""Dependency injection and service container wiring for Praxis CLI."""

from __future__ import annotations

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.task import Task
from praxis_core.errors import AmbiguousIdentifierError, EntityNotFoundError
from praxis_core.intake import CommitmentIntakeEngine
from praxis_core.models.extractor import NebiusTaskExtractor
from praxis_core.persistence import SQLiteUnitOfWork
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
from praxis_cli.migration import JsonStoreMigrator


def get_uow(config: CliConfig) -> SQLiteUnitOfWork:
    """Build SQLiteUnitOfWork for the resolved storage path, migrating legacy JSON if present."""
    config.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if config.legacy_json_path.exists():
        JsonStoreMigrator.migrate_sync(config.legacy_json_path, config.db_url)
    return SQLiteUnitOfWork(config.db_url)


def get_task_extractor() -> TaskExtractor:
    """Build task extractor backed by Nebius with graceful deterministic fallback."""
    return NebiusTaskExtractor()


def make_commitment_intake_engine(config: CliConfig) -> CommitmentIntakeEngine:
    return CommitmentIntakeEngine(
        uow=get_uow(config),
        extractor=get_task_extractor(),
        clock=SystemClock(),
    )


def make_capture_use_case(config: CliConfig) -> CaptureCommitmentUseCase:
    engine = make_commitment_intake_engine(config)
    return CaptureCommitmentUseCase(
        uow=engine.uow,
        extractor=engine.extractor,
        clock=engine.clock,
        engine=engine,
    )


def make_clarify_use_case(config: CliConfig) -> ClarifyCommitmentUseCase:
    engine = make_commitment_intake_engine(config)
    return ClarifyCommitmentUseCase(
        uow=engine.uow,
        extractor=engine.extractor,
        clock=engine.clock,
        engine=engine,
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
    """Resolve an 8-character prefix strictly within the active owner scope."""
    clean_prefix = short_id.strip().lower().replace("-", "")
    matches = await uow.tasks.find_by_id_prefix(clean_prefix, owner_id)
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
    """Resolve an 8-character prefix for commitments strictly within the active owner scope."""
    clean_prefix = short_id.strip().lower().replace("-", "")
    if hasattr(uow.commitments, "find_by_id_prefix"):
        matches = await uow.commitments.find_by_id_prefix(clean_prefix, owner_id)
    else:
        commitments = await uow.commitments.list_by_owner(owner_id)
        matches = [
            c for c in commitments if str(c.id).replace("-", "").lower().startswith(clean_prefix)
        ]
    if not matches:
        raise EntityNotFoundError("Commitment", short_id)
    if len(matches) > 1:
        raise AmbiguousIdentifierError(f"Short ID '{short_id}' matches {len(matches)} commitments.")
    return matches[0]


async def resolve_approval_by_short_id(
    uow: UnitOfWork, short_id: str, owner_id: str
) -> ApprovalRequest:
    """Resolve an 8-character prefix for approvals strictly within the active owner scope."""
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
