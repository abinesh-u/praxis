from __future__ import annotations

import logging
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
from praxis_api.llm_provider import NebiusLLMProvider
from praxis_api.persistence import SQLiteUnitOfWork
from praxis_api.routes import create_api_router
from praxis_api.services import ApiServices
from praxis_api.webhook_runner import WebhookRunner

logger = logging.getLogger(__name__)


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
    skill_store = None
    registry = None

    try:
        from praxis_agent_runtime.adapter import AgentActionDispatcher
        from praxis_agent_runtime.learning.learning_loop import AgentSkillLearner
        from praxis_agent_runtime.skills.skill_store import SkillStore
        from praxis_agent_runtime.tools.builtin.tavily_search import TavilySearchTool
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
        registry.register(TavilySearchTool())
        skill_store = SkillStore(skills_dir)

        agent_dispatcher = AgentActionDispatcher(
            llm=NebiusLLMProvider(),
            tool_registry=registry,
            skill_store=skill_store,
            workspace_root=ws_root,
        )
        router.register_dispatcher("agent_runtime", agent_dispatcher, agent_dispatcher)
        router.register_dispatcher("agent_loop", agent_dispatcher, agent_dispatcher)
        skill_learner = AgentSkillLearner(skill_store=skill_store)
    except Exception:
        logger.warning(
            "Agent runtime unavailable — agent_runtime/agent_loop dispatch disabled.",
            exc_info=True,
        )

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
            skill_store=skill_store,
            tool_registry=registry,
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
