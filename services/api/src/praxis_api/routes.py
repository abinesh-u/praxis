"""Thin FastAPI routes over Praxis core use cases."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from praxis_core.entities.evidence import Evidence
from praxis_core.errors import DomainError, EntityNotFoundError
from praxis_core.use_cases import (
    CaptureCommitmentCommand,
    CompleteTaskCommand,
    ExecuteNextActionCommand,
    ReconcileExecutionCommand,
    ResolveApprovalCommand,
)

from praxis_api.auth import IdentityProvider
from praxis_api.schemas import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalListResponse,
    ApprovalResponse,
    CaptureTaskRequest,
    CaptureTaskResponse,
    CompleteTaskRequest,
    ExecuteTaskRequest,
    ExecutionResponse,
    ReconcileTaskRequest,
    TaskListResponse,
    TaskResponse,
    TodayResponse,
)
from praxis_api.services import ApiServices

ServicesAccessor = Callable[[Request], ApiServices]


def services_from_app_state(request: Request) -> ApiServices:
    """Resolve application services configured by the composition root."""
    try:
        return request.app.state.praxis_services
    except AttributeError as error:
        raise RuntimeError("Praxis API services have not been configured") from error


def identity_from_app_state(request: Request) -> IdentityProvider:
    try:
        return request.app.state.praxis_identity
    except AttributeError:
        return IdentityProvider(tokens={})


def _domain_http_error(error: DomainError) -> HTTPException:
    if isinstance(error, EntityNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    else:
        # Core errors represent safe-to-expose conflicts with current workflow state.
        code = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=code,
        detail={
            "message": error.message,
            "code": error.__class__.__name__,
            "details": error.details,
        },
    )


def create_api_router(
    services_accessor: ServicesAccessor = services_from_app_state,
) -> APIRouter:
    """Create routes bound to an injected service accessor.

    Supplying an accessor keeps route modules independent from FastAPI app startup,
    database configuration, and concrete persistence implementations.
    """

    router = APIRouter()

    def get_services(request: Request) -> ApiServices:
        # Keep FastAPI's dependency signature stable even when tests or an
        # embedding application provide a small unannotated accessor.
        return services_accessor(request)

    @router.post(
        "/tasks",
        response_model=CaptureTaskResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["tasks"],
    )
    async def capture_task(
        body: CaptureTaskRequest,
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> CaptureTaskResponse:
        try:
            owner_id = identity_from_app_state(request).resolve(request, body.owner_id)
            payload = body.model_copy(update={"owner_id": owner_id})
            result = await services.make_capture_commitment().execute(
                CaptureCommitmentCommand(**payload.model_dump())
            )
            return CaptureTaskResponse.from_result(result)
        except DomainError as error:
            raise _domain_http_error(error) from error

    @router.get("/tasks/today", response_model=TodayResponse, tags=["tasks"])
    async def get_today(
        owner_id: Annotated[str, Query(min_length=1, max_length=256)],
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
        at: datetime | None = None,
    ) -> TodayResponse:
        try:
            trusted_owner = identity_from_app_state(request).resolve(request, owner_id)
            result = await services.make_daily_agenda().execute(owner_id=trusted_owner, date=at)
            task_ids = [item.task.id for item in [*result.actionable, *result.waiting]]
            async with services.make_uow() as uow:
                attempts_by_task = await uow.attempts.list_for_tasks(task_ids, trusted_owner)
            return TodayResponse.from_result_with_attempts(result, attempts_by_task)
        except DomainError as error:
            raise _domain_http_error(error) from error

    @router.get("/tasks", response_model=TaskListResponse, tags=["tasks"])
    async def list_tasks(
        owner_id: Annotated[str, Query(min_length=1, max_length=256)],
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> TaskListResponse:
        trusted_owner = identity_from_app_state(request).resolve(request, owner_id)
        async with services.make_uow() as uow:
            raw_tasks = await uow.tasks.list_by_owner(trusted_owner, limit=limit + 1, offset=offset)
        has_more = len(raw_tasks) > limit
        tasks = raw_tasks[:limit]
        return TaskListResponse(
            tasks=[TaskResponse.from_entity(task) for task in tasks],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    @router.get("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
    async def get_task(
        task_id: UUID,
        owner_id: Annotated[str, Query(min_length=1, max_length=256)],
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> TaskResponse:
        trusted_owner = identity_from_app_state(request).resolve(request, owner_id)
        async with services.make_uow() as uow:
            task = await uow.tasks.get_for_owner(task_id, trusted_owner)
        if task is None:
            raise _domain_http_error(EntityNotFoundError("Task", task_id))
        return TaskResponse.from_entity(task)

    @router.post("/tasks/{task_id}/complete", response_model=TaskResponse, tags=["tasks"])
    async def complete_task(
        task_id: UUID,
        body: CompleteTaskRequest,
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> TaskResponse:
        trusted_owner = identity_from_app_state(request).resolve(request, body.owner_id)
        evidence = Evidence.human_confirmed(
            target_task_id=task_id,
            target_action_id=body.target_action_id,
            user_identity=f"api:{trusted_owner}",
            confirmation_note=body.confirmation_note,
        )
        try:
            task = await services.make_complete_task().execute(
                CompleteTaskCommand(task_id=task_id, owner_id=trusted_owner, evidence=evidence)
            )
            return TaskResponse.from_entity(task)
        except DomainError as error:
            raise _domain_http_error(error) from error

    @router.post(
        "/tasks/{task_id}/execute",
        response_model=ExecutionResponse,
        tags=["execution"],
    )
    async def execute_task(
        task_id: UUID,
        body: ExecuteTaskRequest,
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> ExecutionResponse:
        try:
            trusted_owner = identity_from_app_state(request).resolve(request, body.owner_id)
            result = await services.make_execute_next_action().execute(
                ExecuteNextActionCommand(
                    task_id=task_id,
                    owner_id=trusted_owner,
                    idempotency_key=body.idempotency_key,
                    approval_token=body.approval_token,
                    workspace_root=body.workspace_root,
                )
            )
            return ExecutionResponse.from_result(result)
        except DomainError as error:
            raise _domain_http_error(error) from error

    @router.post(
        "/tasks/{task_id}/reconcile",
        response_model=ExecutionResponse,
        tags=["execution"],
    )
    async def reconcile_task(
        task_id: UUID,
        body: ReconcileTaskRequest,
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> ExecutionResponse:
        try:
            trusted_owner = identity_from_app_state(request).resolve(request, body.owner_id)
            result = await services.make_reconcile_execution().execute(
                ReconcileExecutionCommand(
                    task_id=task_id,
                    attempt_id=body.attempt_id,
                    owner_id=trusted_owner,
                )
            )
            return ExecutionResponse.from_result(result)
        except DomainError as error:
            raise _domain_http_error(error) from error

    @router.get("/approvals", response_model=ApprovalListResponse, tags=["approvals"])
    async def list_approvals(
        owner_id: Annotated[str, Query(min_length=1, max_length=256)],
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> ApprovalListResponse:
        trusted_owner = identity_from_app_state(request).resolve(request, owner_id)
        async with services.make_uow() as uow:
            approvals = await uow.approvals.list_pending(trusted_owner)
        return ApprovalListResponse(
            approvals=[ApprovalResponse.from_entity(approval) for approval in approvals]
        )

    @router.post(
        "/approvals/{approval_id}/decision",
        response_model=ApprovalDecisionResponse,
        tags=["approvals"],
    )
    async def decide_approval(
        approval_id: UUID,
        body: ApprovalDecisionRequest,
        request: Request,
        services: Annotated[ApiServices, Depends(get_services)],
    ) -> ApprovalDecisionResponse:
        try:
            trusted_owner = identity_from_app_state(request).resolve(request, body.owner_id)
            result = await services.make_resolve_approval().execute(
                ResolveApprovalCommand(
                    approval_id=approval_id,
                    owner_id=trusted_owner,
                    decision=body.decision,
                    rejection_reason=body.rejection_reason,
                    fatal_rejection=body.fatal_rejection,
                )
            )
            return ApprovalDecisionResponse.from_result(result)
        except DomainError as error:
            raise _domain_http_error(error) from error

    return router
