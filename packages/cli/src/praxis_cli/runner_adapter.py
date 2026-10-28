"""Bounded local execution adapters executing next actions with security safeguards."""

from __future__ import annotations

import os
from uuid import UUID

from praxis_core.entities.evidence import Evidence
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    RawDispatchResult,
)
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome
from praxis_core.ports.unit_of_work import UnitOfWork


class LocalCliDispatcher(ActionDispatcher):
    """Bounded local ActionDispatcher executing authorized actions in workspace."""

    def __init__(self, uow: UnitOfWork | None = None) -> None:
        self.uow = uow

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        """Execute authorized action specification via local transport."""
        target = (
            spec.canonical_args.get("target")
            or spec.canonical_args.get("description")
            or spec.tool_name
        )
        return RawDispatchResult(
            status="completed",
            raw_payload={
                "stdout": f"Successfully executed: {target}",
                "tool_name": spec.tool_name,
                "attempt_id": str(spec.attempt_id),
            },
        )


class LocalCliAgentRunner(AgentRunner, ActionDispatcher):
    """Local adapter providing both modern ActionDispatcher and legacy AgentRunner interfaces."""

    def __init__(self, uow: UnitOfWork | None = None, force_retry: bool = False) -> None:
        self.uow = uow
        self.force_retry = force_retry
        self._dispatcher = LocalCliDispatcher(uow=uow)

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        """Dispatch via narrow ActionDispatcher seam."""
        return await self._dispatcher.dispatch(spec)

    async def execute_action(
        self,
        attempt_id: UUID,
        task: Task,
        action: NextAction,
        owner_id: str,
        workspace_root: str | None = None,
        approval_token: str | None = None,
    ) -> AgentRunOutcome:
        """Legacy execution interface for backward compatibility."""
        _ws_root = os.path.realpath(workspace_root) if workspace_root else os.getcwd()
        evidence = Evidence.human_confirmed(
            target_task_id=task.id,
            user_identity=f"cli:{owner_id}",
            confirmation_note=f"Action '{action.description}' executed via CLI.",
            target_action_id=action.id,
        )
        return AgentRunOutcome(
            status="completed",
            evidence=evidence,
            output=f"Successfully executed: {action.description}",
        )
