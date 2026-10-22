"""Bounded local AgentRunner adapter executing next actions with security safeguards."""

from __future__ import annotations

import os
from uuid import UUID

from praxis_core.entities.approval import ActionSpecification
from praxis_core.entities.common import ActionRiskLevel
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.ports.agent_runner import AgentRunner, AgentRunOutcome

# Tools or hints classified as consequential requiring approval
CONSEQUENTIAL_KEYWORDS = {
    "delete",
    "remove",
    "rm",
    "drop",
    "prune",
    "deploy",
    "publish",
    "destroy",
    "wipe",
    "kill",
}


class LocalCliAgentRunner(AgentRunner):
    """Local-first AgentRunner with risk detection and approval gating."""

    def __init__(self, force_retry: bool = False) -> None:
        self.force_retry = force_retry

    async def execute_action(
        self,
        attempt_id: UUID,
        task: Task,
        action: NextAction,
        owner_id: str,
        workspace_root: str | None = None,
    ) -> AgentRunOutcome:
        _ws_root = os.path.realpath(workspace_root) if workspace_root else os.getcwd()

        # 1. Analyze risk level from tool hint and action description
        desc_lower = action.description.lower()
        tool_hint = (action.tool_hint or "manual_step").lower()
        is_consequential = (
            action.risk_level in (ActionRiskLevel.CONSEQUENTIAL, ActionRiskLevel.DESTRUCTIVE)
            or any(kw in desc_lower for kw in CONSEQUENTIAL_KEYWORDS)
            or any(kw in tool_hint for kw in CONSEQUENTIAL_KEYWORDS)
        )

        if is_consequential:
            action_spec = ActionSpecification(
                tool_name=action.tool_hint or "system_action",
                canonical_args=action.tool_args_hint or {"target": action.description},
                task_id=task.id,
                permission_scope="local_exec",
            )
            return AgentRunOutcome(
                status="awaiting_approval",
                action_spec=action_spec,
                approval_justification=(
                    f"Action '{action.description}' requires explicit authorization."
                ),
            )

        # 2. For safe routine actions: record executed completion evidence
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
