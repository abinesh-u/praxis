"""Dependency contracts for the Praxis HTTP boundary.

The API intentionally owns no persistence or execution wiring.  The application
entry point supplies factories for the core use cases and unit of work so every
request can receive the appropriate transaction-scoped dependencies.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from praxis_core.ports.unit_of_work import UnitOfWork
from praxis_core.use_cases import (
    CaptureCommitmentUseCase,
    CompleteTaskUseCase,
    ExecuteNextActionUseCase,
    GetDailyAgendaUseCase,
    ReconcileExecutionUseCase,
    ResolveApprovalUseCase,
)


@dataclass(frozen=True)
class ApiServices:
    """Factories required by the HTTP routes.

    Factories, rather than singleton use-case instances, keep this boundary
    compatible with request-scoped database unit-of-work implementations.
    """

    make_capture_commitment: Callable[[], CaptureCommitmentUseCase]
    make_complete_task: Callable[[], CompleteTaskUseCase]
    make_daily_agenda: Callable[[], GetDailyAgendaUseCase]
    make_resolve_approval: Callable[[], ResolveApprovalUseCase]
    make_uow: Callable[[], UnitOfWork]
    make_execute_next_action: Callable[[], ExecuteNextActionUseCase]
    make_reconcile_execution: Callable[[], ReconcileExecutionUseCase]
