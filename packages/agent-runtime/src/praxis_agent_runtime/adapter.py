"""Adapter module connecting the agent runtime across the execution seam.

This module exposes the AgentActionDispatcher adapter, which implements the narrow
ActionDispatcher and StatusReconciler interfaces. It leverages procedural skills
from SkillStore while preserving file locality, enforces bounded execution depth,
and coordinates checkpoint recovery across tool perimeters.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    RawDispatchResult,
)
from praxis_core.ports.status_reconciler import (
    RawReconcileResult,
    StatusReconciler,
)

from praxis_agent_runtime.loop.checkpoints import CheckpointStore
from praxis_agent_runtime.loop.conversation_loop import ConversationLoop, LLMProvider, LoopConfig
from praxis_agent_runtime.skills.matcher import match_skills
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.tools.registry import ToolRegistry
from praxis_agent_runtime.types import (
    ApprovalRequired,
    ExecutionStatus,
)


class AgentActionDispatcher(ActionDispatcher, StatusReconciler):
    """Adapter executing actions through the bounded conversation loop interface.

    Leverages keyword triggers for skill locality, enforces strict tool security perimeters,
    and bounds execution depth with explicit step and tool quotas.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        skill_store: SkillStore | None = None,
        checkpoint_store: CheckpointStore | None = None,
        config: LoopConfig | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry or ToolRegistry()
        self._skill_store = skill_store
        self._checkpoint_store = checkpoint_store or CheckpointStore(
            os.path.expanduser("~/.praxis/checkpoints")
        )
        self._config = config or LoopConfig()
        self._workspace_root = workspace_root or os.getcwd()

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        """Dispatch action specification across the narrow agent execution seam."""
        run_id = str(spec.attempt_id)
        existing_run = self._checkpoint_store.load(run_id)

        # Idempotent replay for already-completed run
        if existing_run is not None and existing_run.status == ExecutionStatus.COMPLETED:
            return RawDispatchResult(
                status="completed",
                provider_operation_id=existing_run.run_id,
                raw_payload={
                    "run_id": existing_run.run_id,
                    "status": "completed",
                    "goal": existing_run.goal,
                    "steps": [s.model_dump() for s in existing_run.steps],
                    "tool_evidence": [
                        s.tool_result.evidence
                        for s in existing_run.steps
                        if s.tool_result and s.tool_result.evidence
                    ],
                    "output": (
                        existing_run.steps[-1].content
                        if existing_run.steps
                        else "Execution completed"
                    ),
                },
            )

        goal = (
            spec.canonical_args.get("goal")
            or spec.canonical_args.get("description")
            or spec.canonical_args.get("target")
            or spec.tool_name
        )

        # Skill selection locality: match skills from disk to bound prompt depth
        skill_guides: list[str] = []
        if self._skill_store is not None:
            available_skills = self._skill_store.load_all()
            matched = match_skills(str(goal), available_skills, max_results=3)
            skill_guides = [f"### Skill: {s.name}\n{s.instructions}" for s in matched]

        # Authorize pending tool call if approval token was consumed
        if spec.destination_context.get("approved"):
            approved_tool = spec.canonical_args.get("approved_tool") or spec.tool_name
            approved_args = spec.canonical_args.get("approved_args") or spec.canonical_args
            if approved_tool and approved_tool not in (
                "agent_runtime",
                "agent_loop",
                "system_action",
            ):
                self._tool_registry.grant_approval(approved_tool, approved_args)
            elif existing_run and existing_run.status == ExecutionStatus.AWAITING_APPROVAL:
                for step in reversed(existing_run.steps):
                    if step.step_type == "tool_call" and step.tool_name:
                        self._tool_registry.grant_approval(step.tool_name, step.tool_args or {})
                        break

        # Awaiting approval check when unapproved
        if (
            existing_run is not None
            and existing_run.status == ExecutionStatus.AWAITING_APPROVAL
            and not spec.destination_context.get("approved")
        ):
            pending_tool = None
            pending_args: dict[str, Any] = {}
            for step in reversed(existing_run.steps):
                if step.step_type == "tool_call":
                    pending_tool = step.tool_name
                    pending_args = step.tool_args or {}
                    break
            return RawDispatchResult(
                status="awaiting_approval",
                provider_operation_id=existing_run.run_id,
                raw_payload={
                    "run_id": existing_run.run_id,
                    "tool_name": pending_tool,
                    "tool_args": pending_args,
                    "justification": f"Tool '{pending_tool}' requires approval",
                },
            )

        loop = ConversationLoop(
            llm=self._llm,
            registry=self._tool_registry,
            checkpoint_store=self._checkpoint_store,
            config=self._config,
            skill_guides=skill_guides,
        )

        try:
            run = await asyncio.wait_for(
                asyncio.to_thread(loop.execute, str(goal), run_id),
                timeout=self._config.timeout_seconds,
            )
        except TimeoutError:
            return RawDispatchResult(
                status="outcome_unknown",
                provider_operation_id=run_id,
                error="Agent execution timed out; reconcile before retrying",
            )
        except ApprovalRequired as exc:
            return RawDispatchResult(
                status="awaiting_approval",
                provider_operation_id=run_id,
                raw_payload={
                    "run_id": run_id,
                    "tool_name": exc.tool_name,
                    "tool_args": exc.arguments,
                    "risk_level": exc.risk_level.value,
                    "justification": f"Agent tool '{exc.tool_name}' requires approval.",
                },
            )
        except Exception as exc:
            return RawDispatchResult(
                status="failed",
                provider_operation_id=run_id,
                error=f"Agent loop error: {exc}",
                failure_final=True,
            )

        if run.status == ExecutionStatus.COMPLETED:
            tool_evidence = [
                s.tool_result.evidence
                for s in run.steps
                if s.tool_result and s.tool_result.evidence
            ]
            return RawDispatchResult(
                status="completed",
                provider_operation_id=run.run_id,
                raw_payload={
                    "run_id": run.run_id,
                    "status": "completed",
                    "goal": run.goal,
                    "steps": [s.model_dump() for s in run.steps],
                    "tool_evidence": tool_evidence,
                    "output": run.steps[-1].content if run.steps else "Completed",
                },
            )
        elif run.status == ExecutionStatus.AWAITING_APPROVAL:
            pending_name = None
            pending_args = {}
            for step in reversed(run.steps):
                if step.step_type == "tool_call":
                    pending_name = step.tool_name
                    pending_args = step.tool_args or {}
                    break
            return RawDispatchResult(
                status="awaiting_approval",
                provider_operation_id=run.run_id,
                raw_payload={
                    "run_id": run.run_id,
                    "tool_name": pending_name,
                    "tool_args": pending_args,
                    "justification": f"Tool '{pending_name}' requires approval.",
                },
            )
        else:
            return RawDispatchResult(
                status="failed",
                provider_operation_id=run.run_id,
                error=run.error or "Agent execution failed",
                failure_final=True,
                raw_payload={
                    "run_id": run.run_id,
                    "status": run.status.value,
                    "steps": [s.model_dump() for s in run.steps],
                },
            )

    async def inspect_status(
        self,
        attempt_id: UUID,
        idempotency_key: str,
        provider_operation_id: str | None,
    ) -> RawReconcileResult:
        """Inspect persisted execution checkpoint without triggering side effects."""
        run_id = provider_operation_id or str(attempt_id)
        run = self._checkpoint_store.load(run_id)
        if run is None:
            return RawReconcileResult(
                status="outcome_unknown",
                provider_operation_id=provider_operation_id,
                error="No checkpoint found for attempt",
            )

        if run.status == ExecutionStatus.COMPLETED:
            return RawReconcileResult(
                status="completed",
                provider_operation_id=run.run_id,
                raw_payload={"run_id": run.run_id, "status": "completed"},
            )
        elif run.status in (ExecutionStatus.FAILED, ExecutionStatus.BUDGET_EXHAUSTED):
            return RawReconcileResult(
                status="failed",
                provider_operation_id=run.run_id,
                error=run.error or "Execution failed",
                failure_final=True,
            )
        elif run.status == ExecutionStatus.AWAITING_APPROVAL:
            return RawReconcileResult(
                status="awaiting_approval",
                provider_operation_id=run.run_id,
            )
        else:
            return RawReconcileResult(
                status="outcome_unknown",
                provider_operation_id=run.run_id,
                error="Execution attempt remains in progress or interrupted",
            )
