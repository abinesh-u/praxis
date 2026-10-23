"""Focused tests for the CLI's shared API transport."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from praxis_cli.api_client import (
    PraxisApiClient,
    PraxisApiResponseError,
    PraxisApiUnavailableError,
)
from praxis_cli.config import ConfigError, resolve_api_url, resolve_config


def make_client(handler):
    return PraxisApiClient(
        "http://api.test/",
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://api.test"
        ),
    )


def test_resolve_api_url_defaults_and_config_exposes_it(monkeypatch, tmp_path):
    monkeypatch.delenv("PRAXIS_API_URL", raising=False)
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(tmp_path / "store.json"))

    assert resolve_api_url() == "http://localhost:8000"
    assert resolve_config().api_url == "http://localhost:8000"

    monkeypatch.setenv("PRAXIS_API_URL", "https://praxis.example/api/")
    assert resolve_api_url() == "https://praxis.example/api"


@pytest.mark.parametrize(
    "value", ["", "localhost:8000", "ftp://api.test", "http://user:pass@api.test"]
)
def test_resolve_api_url_rejects_unsafe_or_malformed_values(value, monkeypatch):
    monkeypatch.setenv("PRAXIS_API_URL", value)

    with pytest.raises(ConfigError):
        resolve_api_url()


def test_capture_sends_shared_contract_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tasks"
        assert json.loads(request.content) == {
            "owner_id": "abi",
            "raw_text": "Send the proposal",
            "source": "cli",
            "user_timezone": "Asia/Kolkata",
            "idempotency_key": "capture-1",
        }
        return httpx.Response(201, json={"id": "task-1", "title": "Send the proposal"})

    result = make_client(handler).capture(
        owner_id="abi",
        raw_text="Send the proposal",
        timezone="Asia/Kolkata",
        idempotency_key="capture-1",
    )

    assert result["id"] == "task-1"


def test_retrieval_routes_owner_and_time_parameters():
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url.path == "/tasks/today":
            return httpx.Response(200, json={"spotlight": None, "queue": []})
        if request.url.path == "/tasks/task-1":
            return httpx.Response(200, json={"id": "task-1"})
        return httpx.Response(200, json={"tasks": [{"id": "task-1"}]})

    client = make_client(handler)
    assert client.get_task("task-1", owner_id="abi")["id"] == "task-1"
    assert client.list_tasks(owner_id="abi") == [{"id": "task-1"}]
    assert client.today(owner_id="abi", at=datetime(2026, 10, 23, 9, tzinfo=UTC))["queue"] == []

    assert [str(url) for url in seen] == [
        "http://api.test/tasks/task-1?owner_id=abi",
        "http://api.test/tasks?owner_id=abi",
        "http://api.test/tasks/today?owner_id=abi&at=2026-10-23T09%3A00%3A00%2B00%3A00",
    ]


def test_complete_sends_manual_evidence_note():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tasks/task-1/complete"
        assert json.loads(request.content) == {
            "owner_id": "abi",
            "confirmation_note": "Sent receipt #42",
        }
        return httpx.Response(200, json={"id": "task-1", "status": "completed"})

    completed = make_client(handler).complete_task(
        "task-1", owner_id="abi", note="Sent receipt #42"
    )

    assert completed["status"] == "completed"


def test_complete_supplies_a_human_confirmation_when_note_is_omitted():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "owner_id": "abi",
            "confirmation_note": "Verified completion by user via CLI.",
        }
        return httpx.Response(200, json={"id": "task-1", "status": "completed"})

    make_client(handler).complete_task("task-1", owner_id="abi")


def test_reconcile_posts_attempt_identity_without_dispatch_arguments():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/tasks/task-1/reconcile"
        assert json.loads(request.content) == {
            "owner_id": "abi",
            "attempt_id": "attempt-1",
        }
        return httpx.Response(
            200,
            json={
                "task": {"id": "task-1", "status": "completed"},
                "attempt_id": "attempt-1",
                "attempt_status": "completed",
                "outcome_status": "completed",
            },
        )

    result = make_client(handler).reconcile_task("task-1", owner_id="abi", attempt_id="attempt-1")

    assert result["attempt_status"] == "completed"


def test_reconcile_rejects_an_empty_attempt_id():
    with pytest.raises(ValueError, match="attempt ID must not be empty"):
        make_client(lambda _: httpx.Response(500)).reconcile_task(
            "task-1", owner_id="abi", attempt_id=""
        )


def test_health_and_api_errors_are_safe_and_actionable():
    client = make_client(lambda _: httpx.Response(503, json={"detail": "maintenance"}))

    with pytest.raises(PraxisApiResponseError, match="503.*maintenance") as error:
        client.health()
    assert error.value.status_code == 503

    def offline(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PraxisApiUnavailableError, match="Unable to reach"):
        make_client(offline).health()
