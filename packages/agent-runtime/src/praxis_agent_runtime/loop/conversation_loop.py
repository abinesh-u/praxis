"""Conversation Loop — the Fast Execution Loop."""

from __future__ import annotations

import json
import logging
from typing import Protocol

from praxis_agent_runtime.loop.checkpoints import CheckpointStore
from praxis_agent_runtime.loop.context_compactor import compact_messages, estimate_tokens
from praxis_agent_runtime.parsers.prompt_formatter import build_system_prompt
from praxis_agent_runtime.parsers.tag_parser import extract_tool_calls, format_tool_response
from praxis_agent_runtime.tools.registry import ToolRegistry
from praxis_agent_runtime.types import (
    ApprovalRequired,
    ExecutionStatus,
    RunRecord,
    StepRecord,
)

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """Interface for calling an LLM."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send messages and return the assistant's response text."""
        ...


class LoopConfig:
    """Configuration for the conversation loop."""

    def __init__(
        self,
        max_steps: int = 10,
        max_context_tokens: int = 8_000,
    ) -> None:
        self.max_steps = max_steps
        self.max_context_tokens = max_context_tokens


class ConversationLoop:
    """The Fast Execution Loop."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        checkpoint_store: CheckpointStore,
        config: LoopConfig | None = None,
        skill_guides: list[str] | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._checkpoints = checkpoint_store
        self._config = config or LoopConfig()
        self._skill_guides = skill_guides or []

    def execute(self, goal: str) -> RunRecord:
        """Run the full execution loop for a given goal."""
        run = RunRecord(
            goal=goal,
            max_steps=self._config.max_steps,
            status=ExecutionStatus.RUNNING,
        )
        self._checkpoints.save(run)

        system_prompt = build_system_prompt(
            tools=self._registry.list_tools(),
            skill_guides=self._skill_guides if self._skill_guides else None,
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": goal},
        ]

        step_index = 0

        while step_index < self._config.max_steps:
            messages = compact_messages(
                messages,
                max_tokens=self._config.max_context_tokens,
            )

            try:
                response_text = self._llm.chat(messages)
            except Exception as exc:
                run.status = ExecutionStatus.FAILED
                run.error = f"LLM call failed: {exc}"
                self._checkpoints.save(run)
                return run

            response_tokens = estimate_tokens(response_text)

            try:
                clean_text, tool_calls = extract_tool_calls(response_text)
            except ValueError as exc:
                run.add_step(
                    StepRecord(
                        step_index=step_index,
                        step_type="error",
                        content=f"Failed to parse tool call: {exc}",
                        token_count=response_tokens,
                    )
                )
                run.status = ExecutionStatus.FAILED
                run.error = str(exc)
                self._checkpoints.save(run)
                return run

            run.add_step(
                StepRecord(
                    step_index=step_index,
                    step_type="llm_response",
                    content=clean_text,
                    token_count=response_tokens,
                )
            )
            step_index += 1

            messages.append({"role": "assistant", "content": response_text})

            if not tool_calls:
                run.status = ExecutionStatus.COMPLETED
                self._checkpoints.save(run)
                return run

            for tc in tool_calls:
                run.add_step(
                    StepRecord(
                        step_index=step_index,
                        step_type="tool_call",
                        tool_name=tc.name,
                        tool_args=tc.arguments,
                    )
                )

                try:
                    result = self._registry.execute(tc.name, tc.arguments)
                except ApprovalRequired:
                    run.status = ExecutionStatus.AWAITING_APPROVAL
                    self._checkpoints.save(run)
                    raise

                run.add_step(
                    StepRecord(
                        step_index=step_index,
                        step_type="tool_result",
                        tool_name=tc.name,
                        tool_result=result,
                        content=str(result.output)[:2000] if result.output else None,
                    )
                )
                step_index += 1

                response_json = json.dumps(result.model_dump(), default=str)
                tool_resp_text = format_tool_response(tc.name, response_json)
                messages.append({"role": "user", "content": tool_resp_text})

            self._checkpoints.save(run)

        run.status = ExecutionStatus.BUDGET_EXHAUSTED
        run.error = f"Reached maximum of {self._config.max_steps} steps"
        self._checkpoints.save(run)
        return run
