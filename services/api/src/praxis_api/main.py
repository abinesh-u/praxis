from __future__ import annotations

import os

from fastapi import FastAPI
from praxis_core.models.extractor import NebiusTaskExtractor
from praxis_core.use_cases import (
    CaptureCommitmentUseCase,
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
    runner = WebhookRunner()

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
                uow=make_uow(), runner=runner
            ),
            make_reconcile_execution=lambda: ReconcileExecutionUseCase(
                uow=make_uow(), runner=runner
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
