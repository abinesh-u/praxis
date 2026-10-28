"""HTTP boundary tests using injected in-memory core services."""

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from praxis_api.routes import create_api_router
from praxis_api.services import ApiServices
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, Priority
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from praxis_core.ports.task_extractor import ExtractedTaskData
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases import (
    CaptureCommitmentUseCase,
    ClarifyCommitmentUseCase,
    CompleteTaskUseCase,
    GetDailyAgendaUseCase,
    ResolveApprovalUseCase,
)


class StubExtractor:
    async def extract(self, text: str, reference_time: datetime, user_timezone: str = "UTC"):
        return ExtractedTaskData(
            title="Send project update",
            description=text,
            priority=Priority.IMPORTANT,
            next_action_description="Draft the first sentence",
        )


def make_client() -> tuple[httpx.AsyncClient, InMemoryUnitOfWork]:
    uow = InMemoryUnitOfWork()
    services = ApiServices(
        make_capture_commitment=lambda: CaptureCommitmentUseCase(uow, StubExtractor()),
        make_complete_task=lambda: CompleteTaskUseCase(uow),
        make_daily_agenda=lambda: GetDailyAgendaUseCase(uow),
        make_resolve_approval=lambda: ResolveApprovalUseCase(uow),
        make_uow=lambda: uow,
        make_execute_next_action=lambda: None,
        make_reconcile_execution=lambda: None,
        make_clarify_commitment=lambda: ClarifyCommitmentUseCase(uow, StubExtractor()),
    )
    app = FastAPI()
    app.include_router(create_api_router(lambda _request: services))
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver"), uow


async def capture_task(client: httpx.AsyncClient, owner_id: str = "abi") -> dict:
    response = await client.post(
        "/tasks",
        json={
            "owner_id": owner_id,
            "raw_text": "Send the project update to the team",
            "source": "cli",
            "idempotency_key": f"capture-{owner_id}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.anyio
async def test_capture_get_list_and_today_enforce_owner_boundary():
    client, uow = make_client()
    async with client:
        captured = await capture_task(client)
        task_id = captured["task"]["id"]

        get_response = await client.get(f"/tasks/{task_id}", params={"owner_id": "abi"})
        assert get_response.status_code == 200
        next_action = get_response.json()["current_next_action"]
        assert next_action["description"] == "Draft the first sentence"

        async with uow:
            await uow.attempts.save(
                ExecutionAttempt(
                    owner_id="abi",
                    task_id=UUID(task_id),
                    action_id=UUID(next_action["id"]),
                    idempotency_key="api-agenda-attempt",
                    status="outcome_unknown",
                    provider_request_id="provider-7",
                )
            )
            await uow.commit()

        list_response = await client.get("/tasks", params={"owner_id": "abi"})
        assert list_response.status_code == 200
        assert [task["id"] for task in list_response.json()["tasks"]] == [task_id]

        today_response = await client.get("/tasks/today", params={"owner_id": "abi"})
        assert today_response.status_code == 200
        assert [item["task"]["id"] for item in today_response.json()["actionable"]] == [task_id]
        attempt_summary = today_response.json()["actionable"][0]["attempt"]
        assert attempt_summary["status"] == "outcome_unknown"
        assert attempt_summary["provider_request_id"] == "provider-7"
        assert "idempotency_key" not in attempt_summary

        foreign_response = await client.get(
            f"/tasks/{task_id}", params={"owner_id": "someone-else"}
        )
        assert foreign_response.status_code == 404


@pytest.mark.anyio
async def test_complete_creates_server_owned_human_confirmed_evidence():
    client, uow = make_client()
    async with client:
        task_id = (await capture_task(client))["task"]["id"]

        response = await client.post(
            f"/tasks/{task_id}/complete",
            json={"owner_id": "abi", "confirmation_note": "Sent in the team channel."},
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed"

    # The client cannot forge an arbitrary evidence record; the handler created
    # human-confirmed evidence bound to this exact task.
    saved = await uow.tasks.get_for_owner(UUID(task_id), "abi")
    assert saved is not None
    assert len(saved.evidence_records) == 1


@pytest.mark.anyio
async def test_list_and_decide_pending_approval():
    client, uow = make_client()
    task = Task(owner_id="abi", title="Publish release")
    task.add_next_action("Publish the release")
    task.start()
    task.await_approval("Publishing is external-facing")
    approval, _token = ApprovalRequest.create(
        owner_id="abi",
        task_id=task.id,
        action=ActionSpecification(
            tool_name="release.publish",
            canonical_args={"version": "1.0.0"},
            task_id=task.id,
        ),
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="This will publish version 1.0.0.",
        now=datetime.now(UTC),
    )

    await uow.tasks.save(task)
    await uow.approvals.save(approval)

    async with client:
        list_response = await client.get("/approvals", params={"owner_id": "abi"})
        assert list_response.status_code == 200
        assert list_response.json()["approvals"][0]["id"] == str(approval.id)

        decision_response = await client.post(
            f"/approvals/{approval.id}/decision",
            json={"owner_id": "abi", "decision": "approve"},
        )
        assert decision_response.status_code == 200, decision_response.text
        assert decision_response.json()["approval"]["status"] == "approved"
        assert decision_response.json()["task"]["status"] == "in_progress"

        # Approval list intentionally only exposes un-decided requests.
        assert (await client.get("/approvals", params={"owner_id": "abi"})).json()[
            "approvals"
        ] == []


@pytest.mark.anyio
async def test_clarify_commitment_endpoint():
    client, uow = make_client()
    async with client:
        # First capture
        captured = await capture_task(client)
        commitment_id = captured["commitment"]["id"]

        # Clarify via HTTP route
        clarify_res = await client.post(
            f"/commitments/{commitment_id}/clarify",
            json={
                "owner_id": "abi",
                "clarification_response": "Focus on the frontend release notes",
            },
        )
        assert clarify_res.status_code == 200, clarify_res.text
        data = clarify_res.json()
        assert data["task"]["title"] == "Send project update"
        assert data["clarification_needed"] is False

        # Non-existent commitment returns 404
        missing_res = await client.post(
            "/commitments/00000000-0000-0000-0000-000000000000/clarify",
            json={
                "owner_id": "abi",
                "clarification_response": "details",
            },
        )
        assert missing_res.status_code == 404
