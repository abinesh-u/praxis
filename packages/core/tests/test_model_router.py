"""Unit tests for ModelRouter and profile resolution."""

from praxis_core.models.config import AgentModelSettings, ModelProfile
from praxis_core.models.registry import ModelRegistry
from praxis_core.models.router import ModelRouter


class TestModelRouter:
    def test_default_agent_resolution(self):
        registry = ModelRegistry()
        router = ModelRouter(registry)

        orchestrator_model = router.resolve_model_for_agent("orchestrator")
        assert orchestrator_model.key == "nemotron-3.5-lightning"

        task_extractor_model = router.resolve_model_for_agent("task_extractor")
        assert task_extractor_model.key == "nemotron-3-nano"

        planner_model = router.resolve_model_for_agent("planner")
        assert planner_model.key == "nemotron-3.5-lightning"

    def test_routing_disabled_uses_agent_profile(self):
        registry = ModelRegistry()
        settings = AgentModelSettings(routing_enabled=False)
        router = ModelRouter(registry, settings)

        model = router.route_task("routine extraction task", agent_name="orchestrator")
        assert model.key == "nemotron-3.5-lightning"

    def test_routing_enabled_intent_resolution(self):
        registry = ModelRegistry()
        settings = AgentModelSettings(routing_enabled=True)
        router = ModelRouter(registry, settings)

        routine_model = router.route_task("extract commitments", agent_name="orchestrator")
        assert routine_model.key == "nemotron-3-nano"

        complex_model = router.route_task("plan architecture", agent_name="orchestrator")
        assert complex_model.key == "nemotron-3-super"

        verify_model = router.route_task("verify evidence", agent_name="orchestrator")
        assert verify_model.key == "nemotron-3.5-lightning"

    def test_fallback_when_assigned_model_disabled(self):
        registry = ModelRegistry()
        registry.disable_model("nemotron-3-nano")

        router = ModelRouter(registry)
        model = router.resolve_model_for_profile(ModelProfile.ROUTINE_TASKS.value)
        assert model.key == "nemotron-3.5-lightning"
