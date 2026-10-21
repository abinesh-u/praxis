"""Model configuration schemas and profile definitions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ModelProfile(StrEnum):
    """Standard logical model profiles used by agents."""

    PRIMARY_REASONING = "primary_reasoning"
    ROUTINE_TASKS = "routine_tasks"
    COMPLEX_REASONING = "complex_reasoning"
    VERIFIER = "verifier"


class ModelConfig(BaseModel):
    """Configuration for an individual model."""

    key: str = Field(description="Unique key in registry, e.g. 'nemotron-3.5-lightning'")
    display_name: str = Field(description="Human-readable name")
    provider: str = Field(description="Provider name, e.g. 'nebius'")
    model_id: str = Field(description="Exact provider model identifier")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, gt=0)
    timeout_seconds: int = Field(default=60, gt=0)
    supports_tools: bool = Field(default=True)
    supports_structured_output: bool = Field(default=True)
    enabled: bool = Field(default=True)
    is_verified: bool = Field(
        default=False,
        description="Whether live connectivity/availability has been confirmed",
    )


class AgentModelSettings(BaseModel):
    """Global model assignment and routing settings."""

    default_profile: ModelProfile = Field(default=ModelProfile.PRIMARY_REASONING)
    profile_assignments: dict[str, str] = Field(
        default_factory=lambda: {
            ModelProfile.PRIMARY_REASONING.value: "nemotron-3.5-lightning",
            ModelProfile.ROUTINE_TASKS.value: "nemotron-3-nano",
            ModelProfile.COMPLEX_REASONING.value: "nemotron-3-super",
            ModelProfile.VERIFIER.value: "nemotron-3.5-lightning",
        },
        description="Mapping from profile name to model key",
    )
    agent_assignments: dict[str, str] = Field(
        default_factory=lambda: {
            "orchestrator": ModelProfile.PRIMARY_REASONING.value,
            "task_extractor": ModelProfile.ROUTINE_TASKS.value,
            "planner": ModelProfile.PRIMARY_REASONING.value,
            "verifier": ModelProfile.VERIFIER.value,
        },
        description="Mapping from agent name to profile name",
    )
    routing_enabled: bool = Field(
        default=False,
        description="Whether intent-based automatic model routing is active",
    )
