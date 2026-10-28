from __future__ import annotations

import os

from fastapi import FastAPI
from praxis_core.execution.dispatcher import RoutingActionDispatcher
from praxis_core.models.extractor import NebiusTaskExtractor
from praxis_core.use_cases import (
    CaptureCommitmentUseCase,
    ClarifyCommitmentUseCase,
    CompleteTaskUseCase,
    ExecuteNextActionUseCase,
    GetDailyAgendaUseCase,
    ReconcileExecutionUseCase,
    ResolveApprovalUseCase,
)

from praxis_api.auth import IdentityProvider
from praxis_api.persistence import SQLiteUnitOfWork
from praxis_api.routes import create_api_router
from praxis_api.services import ApiServices
from praxis_api.webhook_runner import WebhookRunner


def create_app(database_url: str | None = None) -> FastAPI:
    """Create the API application and compose request-scoped core services."""
    configured_database_url = database_url or os.environ.get("DATABASE_URL")
    extractor = NebiusTaskExtractor()
    webhook_runner = WebhookRunner()

    # Routing dispatcher adapter coordinating execution across the action seam
    router = RoutingActionDispatcher(
        default_dispatcher=webhook_runner,
        default_reconciler=webhook_runner,
    )
    router.register_dispatcher("webhook_post", webhook_runner, webhook_runner)
    skill_learner = None

    try:
        from praxis_agent_runtime.adapter import AgentActionDispatcher
        from praxis_agent_runtime.learning.learning_loop import AgentSkillLearner
        from praxis_agent_runtime.skills.skill_store import SkillStore
        from praxis_agent_runtime.tools.builtin.workspace_fs import (
            FsListDirTool,
            FsReadFileTool,
            FsWriteFileTool,
        )
        from praxis_agent_runtime.tools.registry import ToolRegistry

        ws_root = os.environ.get("PRAXIS_WORKSPACE_ROOT") or os.getcwd()
        skills_dir = os.environ.get("PRAXIS_SKILLS_DIR") or os.path.expanduser("~/.praxis/skills")
        registry = ToolRegistry()
        registry.register(FsReadFileTool(ws_root))
        registry.register(FsWriteFileTool(ws_root))
        registry.register(FsListDirTool(ws_root))
        skill_store = SkillStore(skills_dir)

        class DefaultLLMProvider:
            """LLM provider adapter leveraging configured model router."""

            def chat(self, messages: list[dict[str, str]]) -> str:
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

        agent_dispatcher = AgentActionDispatcher(
            llm=DefaultLLMProvider(),
            tool_registry=registry,
            skill_store=skill_store,
            workspace_root=ws_root,
        )
        router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)
        router.register_dispatcher("agent_loop", agent_dispatcher, agent_dispatcher)
        skill_learner = AgentSkillLearner(skill_store=skill_store)
    except Exception:
        pass

    runner = router

    def make_uow() -> SQLiteUnitOfWork:
        return SQLiteUnitOfWork(configured_database_url)

    def make_services() -> ApiServices:
        return ApiServices(
            make_capture_commitment=lambda: CaptureCommitmentUseCase(
                uow=make_uow(), extractor=extractor
            ),
            make_complete_task=lambda: CompleteTaskUseCase(uow=make_uow()),
            make_daily_agenda=lambda: GetDailyAgendaUseCase(uow=make_uow()),
            make_resolve_approval=lambda: ResolveApprovalUseCase(uow=make_uow()),
            make_uow=make_uow,
            make_execute_next_action=lambda: ExecuteNextActionUseCase(
                uow=make_uow(), runner=runner, skill_learner=skill_learner
            ),
            make_reconcile_execution=lambda: ReconcileExecutionUseCase(
                uow=make_uow(), runner=runner
            ),
            make_clarify_commitment=lambda: ClarifyCommitmentUseCase(
                uow=make_uow(), extractor=extractor
            ),
        )

    application = FastAPI(
        title="Praxis API",
        description="Shared API for the Praxis CLI and web application.",
        version="0.1.0",
    )
    application.state.praxis_services = make_services()
    application.state.praxis_identity = IdentityProvider.from_environment()
    application.include_router(create_api_router())

    @application.get("/health", tags=["operations"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "praxis-api"}

    return application


app = create_app()
