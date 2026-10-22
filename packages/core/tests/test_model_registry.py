"""Unit tests for ModelRegistry and ModelConfig."""

import pytest
from praxis_core.models.config import ModelConfig
from praxis_core.models.registry import ModelNotFoundError, ModelRegistry


class TestModelRegistry:
    def test_default_models_loaded(self):
        registry = ModelRegistry()
        models = registry.list_models()
        assert len(models) >= 3

        keys = [m.key for m in models]
        assert "nemotron-3.5-lightning" in keys
        assert "nemotron-3-nano" in keys
        assert "nemotron-3-super" in keys

    def test_get_model_success(self):
        registry = ModelRegistry()
        m = registry.get_model("nemotron-3.5-lightning")
        assert m.display_name == "Nemotron 3.5 Lightning"
        assert m.provider == "nebius"
        assert m.model_id == "nvidia/Nemotron-3_5-Lightning"
        assert m.enabled is True

    def test_get_unknown_model_raises(self):
        registry = ModelRegistry()
        with pytest.raises(ModelNotFoundError):
            registry.get_model("nonexistent-model")

    def test_register_new_model(self):
        registry = ModelRegistry()
        new_m = ModelConfig(
            key="custom-model",
            display_name="Custom Model",
            provider="nebius",
            model_id="custom/model-id",
        )
        registry.register_model(new_m)
        assert registry.get_model("custom-model").display_name == "Custom Model"

    def test_register_duplicate_raises(self):
        registry = ModelRegistry()
        with pytest.raises(ValueError, match="already registered"):
            registry.register_model(
                ModelConfig(
                    key="nemotron-3.5-lightning",
                    display_name="Duplicate",
                    provider="nebius",
                    model_id="dup",
                )
            )

    def test_disable_and_enable_model(self):
        registry = ModelRegistry()
        registry.disable_model("nemotron-3-nano")
        assert registry.get_model("nemotron-3-nano").enabled is False
        active_keys = [m.key for m in registry.list_models(include_disabled=False)]
        all_keys = [m.key for m in registry.list_models(include_disabled=True)]
        assert "nemotron-3-nano" not in active_keys
        assert "nemotron-3-nano" in all_keys

        registry.enable_model("nemotron-3-nano")
        assert registry.get_model("nemotron-3-nano").enabled is True
