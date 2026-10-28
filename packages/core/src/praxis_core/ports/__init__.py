"""Ports package for Praxis Core."""

from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    DispatchStatus,
    RawDispatchResult,
)
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome
from praxis_core.ports.approval_repository import (
    ApprovalRepository,
    InMemoryApprovalRepository,
)
from praxis_core.ports.attempt_repository import (
    AttemptRepository,
    InMemoryAttemptRepository,
)
from praxis_core.ports.audit_sink import AuditSink, InMemoryAuditSink
from praxis_core.ports.clock import Clock, FrozenClock, SystemClock
from praxis_core.ports.commitment_repository import (
    CommitmentRepository,
    InMemoryCommitmentRepository,
)
from praxis_core.ports.status_reconciler import (
    RawReconcileResult,
    ReconcileStatus,
    StatusReconciler,
)
from praxis_core.ports.task_extractor import ExtractedTaskData, TaskExtractor
from praxis_core.ports.task_repository import (
    InMemoryTaskRepository,
    TaskRepository,
)
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork, UnitOfWork

__all__ = [
    "ActionDispatcher",
    "AgentRunOutcome",
    "AgentRunner",
    "ApprovalRepository",
    "AttemptRepository",
    "AuditSink",
    "Clock",
    "CommitmentRepository",
    "DispatchSpec",
    "DispatchStatus",
    "ExtractedTaskData",
    "FrozenClock",
    "InMemoryApprovalRepository",
    "InMemoryAttemptRepository",
    "InMemoryAuditSink",
    "InMemoryCommitmentRepository",
    "InMemoryTaskRepository",
    "InMemoryUnitOfWork",
    "RawDispatchResult",
    "RawReconcileResult",
    "ReconcileStatus",
    "StatusReconciler",
    "SystemClock",
    "TaskExtractor",
    "TaskRepository",
    "UnitOfWork",
]
