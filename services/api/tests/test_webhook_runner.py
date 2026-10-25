from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from praxis_api.auth import IdentityProvider
from praxis_api.persistence import SQLiteUnitOfWork
from praxis_api.routes import create_api_router
from praxis_api.services import ApiServices
from praxis_api.webhook_runner import WebhookRunner
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus
from praxis_core.entities.task import Task
from praxis_core.use_cases import ExecuteNextActionUseCase, ReconcileExecutionUseCase


def test_destination_validation_blocks_ssrf_primitives(monkeypatch):
    assert WebhookRunner._validate_destination("file:///tmp/action")
    assert WebhookRunner._validate_destination("http://127.0.0.1/action")
    assert WebhookRunner._validate_destination("http://user:pass@example.com/action")
    monkeypatch.setenv("PRAXIS_WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    assert WebhookRunner._validate_destination("https://other.example.com/action")
    assert WebhookRunner._validate_destination("https://hooks.example.com/action") is None


def test_private_override_requires_explicit_development_environment(monkeypatch):
    monkeypatch.setenv("PRAXIS_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS", "m1-local-only")
    monkeypatch.delenv("APP_ENV", raising=False)
    assert WebhookRunner._validate_destination("http://127.0.0.1/action")
    monkeypatch.setenv("APP_ENV", "development")
    assert WebhookRunner._validate_destination("http://127.0.0.1/action") is None


def test_authenticated_external_http_destination_is_rejected(monkeypatch):
    monkeypatch.setenv("PRAXIS_WEBHOOK_AUTH_TOKEN", "secret")
    monkeypatch.setenv("APP_ENV", "production")
    assert "HTTPS" in (WebhookRunner("http://hooks.example.com/action")._destination_error() or "")


def test_local_override_does_not_allow_authenticated_public_http(monkeypatch):
    monkeypatch.setenv("PRAXIS_WEBHOOK_AUTH_TOKEN", "secret")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PRAXIS_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS", "m1-local-only")
    error = WebhookRunner("http://hooks.example.com/action")._destination_error()
    assert error is not None
    assert "HTTPS" in error


def test_authenticated_loopback_http_is_allowed_for_local_harness(monkeypatch):
    monkeypatch.setenv("PRAXIS_WEBHOOK_AUTH_TOKEN", "secret")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PRAXIS_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS", "m1-local-only")
    assert WebhookRunner("http://127.0.0.1:8765/action")._destination_error() is None


@pytest.mark.anyio
async def test_reconciliation_without_provider_id_never_constructs_a_lookup():
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")
    outcome = await WebhookRunner("https://hooks.example.com/action").reconcile_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        provider_request_id=None,
        idempotency_key="attempt-1",
    )
    assert outcome.status == "outcome_unknown"
    assert "identifier" in (outcome.error or "")


@pytest.mark.anyio
async def test_status_origin_cannot_receive_dispatch_credential(monkeypatch):
    monkeypatch.setenv("PRAXIS_WEBHOOK_AUTH_TOKEN", "dispatch-secret")
    monkeypatch.setenv("PRAXIS_WEBHOOK_STATUS_URL", "https://status.example.com/operations")
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")
    outcome = await WebhookRunner("https://hooks.example.com/action").reconcile_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        provider_request_id="op-1",
        idempotency_key="attempt-1",
    )
    assert outcome.status == "outcome_unknown"
    assert "separate status credential" in (outcome.error or "")


@pytest.mark.anyio
async def test_status_origin_uses_separate_credential(monkeypatch):
    monkeypatch.setenv("PRAXIS_WEBHOOK_AUTH_TOKEN", "dispatch-secret")
    monkeypatch.setenv("PRAXIS_WEBHOOK_STATUS_AUTH_TOKEN", "status-secret")
    monkeypatch.setenv("PRAXIS_WEBHOOK_STATUS_URL", "https://status.example.com/operations")
    captured: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"operation_id": "op-1", "status": "completed"})

    runner = WebhookRunner(
        "https://hooks.example.com/action", transport=httpx.MockTransport(provider)
    )
    monkeypatch.setattr(runner, "_resolved_destination_error", lambda _url: _none())
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")
    outcome = await runner.reconcile_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        provider_request_id="op-1",
        idempotency_key="attempt-1",
    )
    assert outcome.status == "completed"
    assert captured[0].headers["Authorization"] == "Bearer status-secret"


@pytest.mark.anyio
async def test_authoritative_dispatch_failure_is_not_marked_unknown(monkeypatch):
    async def provider(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"status": "failed", "failure_final": True, "error": "rejected"},
            headers={"X-Operation-ID": "op-rejected"},
            request=request,
        )

    runner = WebhookRunner(
        "https://hooks.example.com/action", transport=httpx.MockTransport(provider)
    )
    monkeypatch.setattr(runner, "_resolved_destination_error", lambda _url: _none())
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")
    outcome = await runner.execute_action(
        attempt_id=uuid4(), task=task, action=action, owner_id="owner", approval_token="approved"
    )
    assert outcome.status == "failed"
    assert outcome.provider_request_id == "op-rejected"


@pytest.mark.anyio
async def test_invalid_provider_id_is_not_used_as_a_status_path():
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")
    outcome = await WebhookRunner("https://hooks.example.com/action").reconcile_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        provider_request_id="../../metadata",
        idempotency_key="attempt-1",
    )
    assert outcome.status == "outcome_unknown"
    assert "invalid" in (outcome.error or "")


@pytest.mark.anyio
async def test_provider_redirect_is_not_followed(monkeypatch):
    calls: list[str] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "https://unapproved.example.com/redirected"},
            request=request,
        )

    runner = WebhookRunner(
        "https://hooks.example.com/action", transport=httpx.MockTransport(provider)
    )

    async def no_dns(_url: str) -> None:
        return None

    monkeypatch.setattr(runner, "_resolved_destination_error", no_dns)
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")
    outcome = await runner.execute_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        approval_token="approved-token",
    )

    assert outcome.status == "outcome_unknown"
    assert calls == ["https://hooks.example.com/action"]


@pytest.mark.anyio
async def test_timeout_then_reconcile_uses_get_without_a_second_post(monkeypatch):
    calls: list[str] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("simulated acceptance timeout", request=request)
        return httpx.Response(200, json={"operation_id": "op-1", "status": "completed"})

    runner = WebhookRunner(
        "https://hooks.example.com/action", transport=httpx.MockTransport(provider)
    )
    monkeypatch.setattr(runner, "_resolved_destination_error", lambda _url: _none())
    task = Task(owner_id="owner", title="Notify")
    action = task.add_next_action("Send notification", tool_hint="webhook_post")

    first = await runner.execute_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        approval_token="approved-token",
    )
    reconciled = await runner.reconcile_action(
        attempt_id=uuid4(),
        task=task,
        action=action,
        owner_id="owner",
        provider_request_id="op-1",
        idempotency_key="attempt-1",
    )

    assert first.status == "outcome_unknown"
    assert reconciled.status == "completed"
    assert calls == ["POST", "GET"]


class AcceptedThenTimeoutStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise httpx.ReadTimeout("accepted before response body", request=None)
        yield b""  # pragma: no cover


@pytest.mark.anyio
async def test_controlled_provider_timeout_restart_and_reconcile(tmp_path, monkeypatch):
    """A provider acceptance timeout survives restart and reconciles with one POST."""
    calls: list[str] = []
    operation_id = "op-controlled-42"

    async def provider(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(
                200,
                headers={"X-Operation-ID": operation_id},
                stream=AcceptedThenTimeoutStream(),
                request=request,
            )
        assert request.method == "GET"
        return httpx.Response(200, json={"operation_id": operation_id, "status": "completed"})

    transport = httpx.MockTransport(provider)
    runner = WebhookRunner("https://hooks.example.com/action", transport=transport, timeout=1)

    async def no_dns(_url: str) -> None:
        return None

    monkeypatch.setattr(runner, "_resolved_destination_error", no_dns)
    database_url = f"sqlite:///{tmp_path / 'controlled.db'}"
    task = Task(owner_id="abi", title="Send controlled update")
    action = task.add_next_action(
        "Send update", tool_hint="webhook_post", tool_args_hint={"message": "hello"}
    )
    spec = ActionSpecification(
        tool_name="webhook_post",
        canonical_args=action.tool_args_hint or {},
        task_id=task.id,
        permission_scope="external_http",
    )
    approval, token = ApprovalRequest.create(
        owner_id="abi",
        task_id=task.id,
        action=spec,
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="Controlled provider test",
    )
    approval.status = ApprovalStatus.APPROVED

    async with SQLiteUnitOfWork(database_url) as uow:
        await uow.tasks.save(task)
        await uow.approvals.save(approval)
        await uow.commit()

    def make_app() -> FastAPI:
        def make_uow() -> SQLiteUnitOfWork:
            return SQLiteUnitOfWork(database_url)

        services = ApiServices(
            make_capture_commitment=lambda: None,
            make_complete_task=lambda: None,
            make_daily_agenda=lambda: None,
            make_resolve_approval=lambda: None,
            make_uow=make_uow,
            make_execute_next_action=lambda: ExecuteNextActionUseCase(make_uow(), runner),
            make_reconcile_execution=lambda: ReconcileExecutionUseCase(make_uow(), runner),
        )
        app = FastAPI()
        app.state.praxis_identity = IdentityProvider(tokens={})
        app.include_router(create_api_router(lambda _request: services))
        return app

    # First process: dispatch reaches provider, but response body times out.
    async with httpx.AsyncClient(
        transport=ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/tasks/{task.id}/execute",
            json={
                "owner_id": "abi",
                "idempotency_key": "controlled-attempt",
                "approval_token": token,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["attempt_status"] == "outcome_unknown"
        assert payload["provider_request_id"] == operation_id
        attempt_id = payload["attempt_id"]

    # Second process: same database, read-only reconciliation, no second POST.
    async with httpx.AsyncClient(
        transport=ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/tasks/{task.id}/reconcile",
            json={"owner_id": "abi", "attempt_id": attempt_id},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["attempt_status"] == "completed"
        assert payload["provider_request_id"] == operation_id

    assert calls == ["POST", "GET"]
    async with SQLiteUnitOfWork(database_url) as uow:
        persisted_attempt = await uow.attempts.get_for_owner(UUID(attempt_id), "abi")
        assert persisted_attempt is not None
        assert persisted_attempt.status == "completed"
        assert persisted_attempt.evidence_id is not None
        persisted_task = await uow.tasks.get_for_owner(task.id, "abi")
        assert persisted_task is not None
        assert persisted_task.status.value == "completed"
        assert persisted_task.evidence_records
        events = await uow.audit_sink.list_for_aggregate(task.id)
        assert any(event.event_type == "task.completed" for event in events)


async def _none() -> None:
    return None
