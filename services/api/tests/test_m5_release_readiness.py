"""Milestone M5 release readiness and adversarial operational tests.

Verifies tenant isolation, token authentication, and execution safety:
1. Rejection of unauthenticated and mismatched tenant identity claims across the seam.
2. Cross-tenant denial for all protected operations (inspect, complete, execute, approve).
3. Replay protection, argument tampering detection, and repeated decision rejection.
4. Strictly read-only status reconciliation preventing duplicate side effects.
"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from praxis_api.main import create_app
from praxis_api.persistence import SQLiteUnitOfWork
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus, Priority, TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from praxis_core.ports.task_extractor import ExtractedTaskData


class MockExtractor:
    async def extract(self, text: str, reference_time: datetime, user_timezone: str = "UTC"):
        return ExtractedTaskData(
            title="Isolated Task",
            description=text,
            priority=Priority.IMPORTANT,
            next_action_description="Execute isolated action",
            tool_hint="webhook_post",
            tool_args_hint={"url": "https://example.com/action"},
        )


def _client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.anyio
async def test_authentication_error_semantics_401_and_403(tmp_path, monkeypatch):
    """Missing or invalid credentials return 401; mismatched identity returns 403."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'auth_errors.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    # 1. Missing Authorization header -> 401
    res_no_auth = await client.get("/tasks/today", params={"owner_id": "alice"})
    assert res_no_auth.status_code == 401
    assert "Bearer" in res_no_auth.headers.get("www-authenticate", "")

    # 2. Invalid Bearer token -> 401
    res_bad_token = await client.get(
        "/tasks/today",
        params={"owner_id": "alice"},
        headers={"Authorization": "Bearer bad_secret"},
    )
    assert res_bad_token.status_code == 401

    # 3. Valid Bob token claiming Alice's identity -> 403 Forbidden
    res_mismatched = await client.get(
        "/tasks/today",
        params={"owner_id": "alice"},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res_mismatched.status_code == 403
    assert "not match" in res_mismatched.json()["detail"].lower()


@pytest.mark.anyio
async def test_cross_tenant_task_access_denied(tmp_path, monkeypatch):
    """Authenticated tenant Bob cannot inspect Alice's tasks (returns 404)."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'isolation_tasks.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    # Create task for Alice
    uow = SQLiteUnitOfWork(db_path)
    alice_task = Task(owner_id="alice", title="Alice Private Plan")
    async with uow:
        await uow.tasks.save(alice_task)
        await uow.commit()

    # Bob attempts to inspect Alice's task
    res = await client.get(
        f"/tasks/{alice_task.id}",
        params={"owner_id": "bob"},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res.status_code == 404


@pytest.mark.anyio
async def test_cross_tenant_task_completion_denied(tmp_path, monkeypatch):
    """Authenticated tenant Bob cannot complete Alice's task."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'isolation_complete.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    uow = SQLiteUnitOfWork(db_path)
    alice_task = Task(owner_id="alice", title="Alice In-Progress Task")
    alice_task.start()
    async with uow:
        await uow.tasks.save(alice_task)
        await uow.commit()

    res = await client.post(
        f"/tasks/{alice_task.id}/complete",
        json={"owner_id": "bob", "confirmation_note": "Bob claims completion"},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res.status_code == 404

    # Verify Alice's task remains in progress
    async with uow:
        check = await uow.tasks.get_for_owner(alice_task.id, "alice")
        assert check is not None
        assert check.status == TaskStatus.IN_PROGRESS


@pytest.mark.anyio
async def test_cross_tenant_action_execution_denied(tmp_path, monkeypatch):
    """Authenticated tenant Bob cannot dispatch execution for Alice's task."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'isolation_execute.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    uow = SQLiteUnitOfWork(db_path)
    alice_task = Task(owner_id="alice", title="Alice Actionable Task")
    alice_task.add_next_action("Alice Next Action")
    async with uow:
        await uow.tasks.save(alice_task)
        await uow.commit()

    res = await client.post(
        f"/tasks/{alice_task.id}/execute",
        json={"owner_id": "bob", "idempotency_key": "bob-exec-key"},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res.status_code == 404


@pytest.mark.anyio
async def test_cross_tenant_reconciliation_denied(tmp_path, monkeypatch):
    """Authenticated tenant Bob cannot reconcile Alice's execution attempt."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'isolation_reconcile.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    uow = SQLiteUnitOfWork(db_path)
    alice_task = Task(owner_id="alice", title="Alice Task with Attempt")
    action = alice_task.add_next_action("Alice Action")
    attempt = ExecutionAttempt(
        owner_id="alice",
        task_id=alice_task.id,
        action_id=action.id,
        idempotency_key="alice-attempt-key",
        status="outcome_unknown",
        provider_request_id="prov-123",
    )
    async with uow:
        await uow.tasks.save(alice_task)
        await uow.attempts.save(attempt)
        await uow.commit()

    res = await client.post(
        f"/tasks/{alice_task.id}/reconcile",
        json={"owner_id": "bob", "attempt_id": str(attempt.id)},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res.status_code == 404


@pytest.mark.anyio
async def test_cross_tenant_approval_decision_denied(tmp_path, monkeypatch):
    """Authenticated tenant Bob cannot decide Alice's approval request."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'isolation_approval.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    uow = SQLiteUnitOfWork(db_path)
    alice_task = Task(owner_id="alice", title="Alice Consequential Task")
    alice_task.add_next_action("Consequential Action")
    alice_task.start()
    alice_task.await_approval("Consequential webhook")

    approval, _raw_token = ApprovalRequest.create(
        owner_id="alice",
        task_id=alice_task.id,
        action=ActionSpecification(
            tool_name="webhook_post",
            canonical_args={"url": "https://api.external.com/pay"},
            task_id=alice_task.id,
        ),
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="Sensitive payment",
        now=datetime.now(UTC),
    )

    async with uow:
        await uow.tasks.save(alice_task)
        await uow.approvals.save(approval)
        await uow.commit()

    res = await client.post(
        f"/approvals/{approval.id}/decision",
        json={"owner_id": "bob", "decision": "approve"},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res.status_code == 404

    # Verify Alice's approval remains pending
    async with uow:
        check = await uow.approvals.get_for_owner(approval.id, "alice")
        assert check is not None
        assert check.status == ApprovalStatus.PENDING


@pytest.mark.anyio
async def test_repeated_approval_decision_fails_closed(tmp_path, monkeypatch):
    """An approved or rejected request cannot be decided a second time (fails closed with 409)."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice")
    db_path = f"sqlite:///{tmp_path / 'repeat_approval.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    uow = SQLiteUnitOfWork(db_path)
    task = Task(owner_id="alice", title="Action requiring approval")
    task.add_next_action("Action")
    task.start()
    task.await_approval("Consequential operation")

    approval, _ = ApprovalRequest.create(
        owner_id="alice",
        task_id=task.id,
        action=ActionSpecification(
            tool_name="webhook_post",
            canonical_args={"param": 1},
            task_id=task.id,
        ),
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="Need authorization",
        now=datetime.now(UTC),
    )
    async with uow:
        await uow.tasks.save(task)
        await uow.approvals.save(approval)
        await uow.commit()

    # 1. First decision: approve succeeds
    res_1 = await client.post(
        f"/approvals/{approval.id}/decision",
        json={"owner_id": "alice", "decision": "approve"},
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res_1.status_code == 200
    assert res_1.json()["approval"]["status"] == "approved"

    # 2. Second decision attempt: fails closed with 409 Conflict
    res_2 = await client.post(
        f"/approvals/{approval.id}/decision",
        json={"owner_id": "alice", "decision": "reject"},
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res_2.status_code == 409
    assert "cannot" in res_2.json()["detail"]["message"].lower()


@pytest.mark.anyio
async def test_idempotent_capture_fingerprint_tampering_rejected(tmp_path, monkeypatch):
    """Replaying capture with the same idempotency key but altered text raises conflict."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice")
    db_path = f"sqlite:///{tmp_path / 'tamper_capture.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    # First capture
    res_1 = await client.post(
        "/tasks",
        json={
            "owner_id": "alice",
            "raw_text": "Original commitment text",
            "idempotency_key": "unique-idem-1",
        },
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res_1.status_code == 201

    # Exact replay succeeds
    res_replay = await client.post(
        "/tasks",
        json={
            "owner_id": "alice",
            "raw_text": "Original commitment text",
            "idempotency_key": "unique-idem-1",
        },
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res_replay.status_code == 201
    assert res_replay.json()["task"]["id"] == res_1.json()["task"]["id"]

    # Tampered replay with different content raises 409
    res_tampered = await client.post(
        "/tasks",
        json={
            "owner_id": "alice",
            "raw_text": "Tampered malicious commitment text",
            "idempotency_key": "unique-idem-1",
        },
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res_tampered.status_code == 409


@pytest.mark.anyio
async def test_cross_tenant_commitment_clarification_denied(tmp_path, monkeypatch):
    """Authenticated tenant Bob cannot clarify Alice's ambiguous commitment."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice,bob=token_bob")
    db_path = f"sqlite:///{tmp_path / 'isolation_clarify.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    # Alice captures ambiguous commitment
    res = await client.post(
        "/tasks",
        json={"owner_id": "alice", "raw_text": "Review it"},
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res.status_code == 201
    commitment_id = res.json()["commitment"]["id"]

    # Bob attempts to clarify Alice's commitment
    res_bob = await client.post(
        f"/commitments/{commitment_id}/clarify",
        json={"owner_id": "bob", "clarification_response": "Bob's malicious clarification"},
        headers={"Authorization": "Bearer token_bob"},
    )
    assert res_bob.status_code == 404


@pytest.mark.anyio
async def test_duplicate_execution_preserves_attempt_idempotency(tmp_path, monkeypatch):
    """Duplicate execution dispatch returns existing attempt without generating new attempts."""
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "alice=token_alice")
    db_path = f"sqlite:///{tmp_path / 'dup_exec.db'}"
    app = create_app(db_path)
    client = _client_for(app)

    uow = SQLiteUnitOfWork(db_path)
    task = Task(owner_id="alice", title="Task with completed attempt")
    action = task.add_next_action("Completed Action")
    task.start()
    attempt = ExecutionAttempt(
        owner_id="alice",
        task_id=task.id,
        action_id=action.id,
        idempotency_key="alice-idem-key",
        status="completed",
        provider_request_id="prov-1",
    )
    async with uow:
        await uow.tasks.save(task)
        await uow.attempts.save(attempt)
        await uow.commit()

    # Dispatch execution with the same idempotency key
    res = await client.post(
        f"/tasks/{task.id}/execute",
        json={"owner_id": "alice", "idempotency_key": "alice-idem-key"},
        headers={"Authorization": "Bearer token_alice"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["attempt_id"] == str(attempt.id)
    assert data["attempt_status"] == "completed"

    # Verify only 1 attempt exists in storage
    async with uow:
        attempts = await uow.attempts.list_for_task(task.id, "alice")
        assert len(attempts) == 1
        assert attempts[0].id == attempt.id


@pytest.mark.anyio
async def test_reconciliation_is_strictly_read_only_and_never_dispatches():
    """Reconciliation only queries status by observation and never dispatches side effects."""
    from praxis_core.ports.action_dispatcher import (
        ActionDispatcher,
        DispatchSpec,
        RawDispatchResult,
    )
    from praxis_core.ports.status_reconciler import RawReconcileResult, StatusReconciler
    from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
    from praxis_core.use_cases.reconcile_execution import (
        ReconcileExecutionCommand,
        ReconcileExecutionUseCase,
    )

    class SpyDispatcherAndReconciler(ActionDispatcher, StatusReconciler):
        def __init__(self):
            self.dispatch_call_count = 0
            self.reconcile_call_count = 0

        async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
            self.dispatch_call_count += 1
            return RawDispatchResult(status="completed")

        async def inspect_status(
            self, attempt_id, idempotency_key, provider_operation_id=None, **kwargs
        ):
            self.reconcile_call_count += 1
            return RawReconcileResult(
                status="completed",
                authoritative=True,
                provider_operation_id=provider_operation_id or "prov-rec-1",
                raw_payload={"status": "completed", "operation_id": "prov-rec-1"},
            )

    uow = InMemoryUnitOfWork()
    runner = SpyDispatcherAndReconciler()
    task = Task(owner_id="alice", title="Unreconciled Task")
    action = task.add_next_action("Action in progress")
    task.start()
    attempt = ExecutionAttempt(
        owner_id="alice",
        task_id=task.id,
        action_id=action.id,
        idempotency_key="reconcile-check-key",
        status="outcome_unknown",
        provider_request_id="prov-rec-1",
    )
    async with uow:
        await uow.tasks.save(task)
        await uow.attempts.save(attempt)
        await uow.commit()

    use_case = ReconcileExecutionUseCase(uow=uow, reconciler=runner)
    result = await use_case.execute(
        ReconcileExecutionCommand(
            task_id=task.id,
            attempt_id=attempt.id,
            owner_id="alice",
        )
    )

    # Reconcile was called once, dispatch was NEVER called
    assert runner.reconcile_call_count == 1
    assert runner.dispatch_call_count == 0
    assert result.outcome.status == "completed"
