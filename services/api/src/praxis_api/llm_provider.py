"""NebiusLLMProvider — named adapter satisfying the agent-runtime LLMProvider interface.

This module exposes a concrete, importable, independently-testable adapter so that
the LLMProvider seam in praxis_agent_runtime.adapter has two real adapters
(this one plus test doubles) rather than a single anonymous class defined inline
inside create_app().
"""

from __future__ import annotations

import os


class NebiusLLMProvider:
    """LLM provider adapter leveraging the configured Nebius model router.

    Satisfies the ``LLMProvider`` protocol expected by ``AgentActionDispatcher``.
    Reads ``NEBIUS_API_KEY`` from the environment at call time so the application
    can start before the key is available (e.g. during migrations or health checks).
    """

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request through the Nebius Token Factory.

        Returns the model's text response, or a clear error string when the API
        key is absent — never raises so callers get a degraded but observable
        outcome rather than an unhandled exception.
        """
        api_key = os.getenv("NEBIUS_API_KEY", "")
        if not api_key:
            return "No API key configured for agent runtime."

        from praxis_core.models.providers.base import NormalizedCompletionRequest
        from praxis_core.models.providers.nebius import NebiusTokenFactoryAdapter
        from praxis_core.models.registry import ModelRegistry
        from praxis_core.models.router import ModelRouter

        model_router = ModelRouter(registry=ModelRegistry())
        cfg = model_router.resolve_model_for_profile("routine_tasks")
        model_adapter = NebiusTokenFactoryAdapter(config=cfg, api_key=api_key)
        return model_adapter.invoke(NormalizedCompletionRequest(messages=messages)).text
