"""End-to-end coverage for the composed API application and durable store."""

import httpx
import pytest
from praxis_api.main import create_app


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.anyio
async def test_capture_and_completion_survive_new_application_instance(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'praxis.db'}"
    first = client_for(create_app(database_url))

    async with first:
        captured = await first.post(
            "/tasks",
            json={
                "owner_id": "api-user",
                "raw_text": "Send the project update",
                "source": "cli",
                "idempotency_key": "capture-1",
            },
        )
    assert captured.status_code == 201, captured.text
    task = captured.json()["task"]

    async with client_for(create_app(database_url)) as first:
        completed = await first.post(
            f"/tasks/{task['id']}/complete",
            json={"owner_id": "api-user", "confirmation_note": "Sent to the team channel."},
        )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"

    async with client_for(create_app(database_url)) as second:
        loaded = await second.get(f"/tasks/{task['id']}", params={"owner_id": "api-user"})
    assert loaded.status_code == 200
    assert loaded.json()["status"] == "completed"

    async with client_for(create_app(database_url)) as second:
        replay = await second.post(
            "/tasks",
            json={
                "owner_id": "api-user",
                "raw_text": "Send the project update",
                "source": "cli",
                "idempotency_key": "capture-1",
            },
        )
    assert replay.status_code == 201
    assert replay.json()["task"]["id"] == task["id"]


@pytest.mark.anyio
async def test_configured_bearer_identity_controls_owner_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAXIS_AUTH_TOKENS", "api-user=secret-token")
    app = create_app(f"sqlite:///{tmp_path / 'auth.db'}")
    client = client_for(app)
    payload = {
        "owner_id": "api-user",
        "raw_text": "Capture an authenticated task",
        "source": "api",
    }

    async with client:
        missing = await client.post("/tasks", json=payload)
    assert missing.status_code == 401

    async with client_for(app) as client:
        mismatch = await client.post(
            "/tasks",
            json={**payload, "owner_id": "other-user"},
            headers={"Authorization": "Bearer secret-token"},
        )
    assert mismatch.status_code == 403

    async with client_for(app) as client:
        accepted = await client.post(
            "/tasks", json=payload, headers={"Authorization": "Bearer secret-token"}
        )
    assert accepted.status_code == 201, accepted.text
