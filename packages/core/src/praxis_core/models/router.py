"""Model Router — resolves model profiles and handles intent-based routing."""

from __future__ import annotations

import logging

from praxis_core.models.config import AgentModelSettings, ModelConfig, ModelProfile
from praxis_core.models.registry import ModelRegistry

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes execution requests to the appropriate model based on agent profile or intent."""

    def __init__(
        self,
        registry: ModelRegistry,
        settings: AgentModelSettings | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings or AgentModelSettings()

    def resolve_model_for_agent(self, agent_name: str) -> ModelConfig:
        """Resolve the model configuration assigned to a specific agent."""
        profile_name = self.settings.agent_assignments.get(
            agent_name,
            self.settings.default_profile.value,
        )
        return self.resolve_model_for_profile(profile_name)

    def resolve_model_for_profile(self, profile_name: str) -> ModelConfig:
        """Resolve model configuration for a logical profile with fallback support."""
        model_key = self.settings.profile_assignments.get(profile_name)

        if not model_key:
            # Fall back to default profile assignment
            model_key = self.settings.profile_assignments.get(
                self.settings.default_profile.value,
            )

        if not model_key:
            raise ValueError(f"No model assigned to profile '{profile_name}'")

        model = self.registry.get_model(model_key)

        if not model.enabled:
            # Attempt fallback to primary reasoning model
            default_key = self.settings.profile_assignments.get(
                ModelProfile.PRIMARY_REASONING.value,
            )
            if default_key and default_key != model_key:
                fallback = self.registry.get_model(default_key)
                if fallback.enabled:
                    logger.warning(
                        "Model '%s' is disabled; falling back to primary reasoning '%s'",
                        model_key,
                        default_key,
                    )
                    return fallback
            raise ValueError(f"Model '{model_key}' assigned to '{profile_name}' is disabled")

        return model

    def route_task(self, intent: str, agent_name: str | None = None) -> ModelConfig:
        """Route a task dynamically if routing is enabled; otherwise use agent assignment."""
        if not self.settings.routing_enabled:
            target_agent = agent_name or "orchestrator"
            return self.resolve_model_for_agent(target_agent)

        intent_lower = intent.lower()

        if any(w in intent_lower for w in ["routine", "extract", "parse", "classify", "summarize"]):
            return self.resolve_model_for_profile(ModelProfile.ROUTINE_TASKS.value)
        elif any(
            w in intent_lower for w in ["complex", "plan", "strategy", "architecture", "solve"]
        ):
            return self.resolve_model_for_profile(ModelProfile.COMPLEX_REASONING.value)
        elif any(w in intent_lower for w in ["verify", "audit", "check", "test"]):
            return self.resolve_model_for_profile(ModelProfile.VERIFIER.value)
        else:
            return self.resolve_model_for_profile(ModelProfile.PRIMARY_REASONING.value)
