"""Model Registry — maintains the catalog of configured models."""

from __future__ import annotations

import copy
from typing import Any

from praxis_core.models.config import ModelConfig


class ModelNotFoundError(Exception):
    """Raised when a requested model key does not exist."""


class ModelRegistry:
    """Registry maintaining available and configured models."""

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        defaults = [
            ModelConfig(
                key="nemotron-3.5-lightning",
                display_name="Nemotron 3.5 Lightning",
                provider="nebius",
                model_id="nvidia/Nemotron-3_5-Lightning",
                temperature=0.2,
                max_output_tokens=4096,
                timeout_seconds=60,
                supports_tools=True,
                supports_structured_output=True,
                enabled=True,
                is_verified=True,
            ),
            ModelConfig(
                key="nemotron-3-nano",
                display_name="Nemotron 3 Nano",
                provider="nebius",
                model_id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
                temperature=0.1,
                max_output_tokens=2048,
                timeout_seconds=30,
                supports_tools=True,
                supports_structured_output=True,
                enabled=True,
                is_verified=False,
            ),
            ModelConfig(
                key="nemotron-3-super",
                display_name="Nemotron 3 Super",
                provider="nebius",
                model_id="nvidia/nemotron-3-super-120b-a12b",
                temperature=0.3,
                max_output_tokens=8192,
                timeout_seconds=120,
                supports_tools=True,
                supports_structured_output=True,
                enabled=True,
                is_verified=False,
            ),
        ]
        for m in defaults:
            self._models[m.key] = m

    def list_models(self, include_disabled: bool = False) -> list[ModelConfig]:
        """List registered models."""
        models = [copy.deepcopy(m) for m in self._models.values()]
        if not include_disabled:
            models = [m for m in models if m.enabled]
        return models

    def get_model(self, key: str) -> ModelConfig:
        """Get model configuration by key."""
        if key not in self._models:
            raise ModelNotFoundError(f"Model '{key}' is not in the registry")
        return copy.deepcopy(self._models[key])

    def register_model(self, config: ModelConfig) -> None:
        """Register a new model configuration."""
        if config.key in self._models:
            raise ValueError(f"Model with key '{config.key}' already registered")
        self._models[config.key] = copy.deepcopy(config)

    def update_model(self, key: str, updates: dict[str, Any]) -> ModelConfig:
        """Update an existing model's configuration."""
        if key not in self._models:
            raise ModelNotFoundError(f"Model '{key}' is not in the registry")

        current = self._models[key].model_dump()
        current.update(updates)
        updated = ModelConfig.model_validate(current)
        self._models[key] = updated
        return copy.deepcopy(updated)

    def disable_model(self, key: str) -> None:
        """Disable a model."""
        self.update_model(key, {"enabled": False})

    def enable_model(self, key: str) -> None:
        """Enable a model."""
        self.update_model(key, {"enabled": True})
