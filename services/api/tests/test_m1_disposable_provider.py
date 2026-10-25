from __future__ import annotations

import importlib.util
from pathlib import Path
from threading import Thread
from typing import Any

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "m1_disposable_provider.py"


def load_provider() -> Any:
    spec = importlib.util.spec_from_file_location("m1_disposable_provider", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def reject_provider():
    module = load_provider()
    module.TOKEN = "test-token"
    module.MODE = "reject"
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.ProviderHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_reject_mode_persists_final_failure_without_an_effect(reject_provider: str) -> None:
    headers = {"Authorization": "Bearer test-token", "Idempotency-Key": "attempt-1"}
    with httpx.Client(timeout=2.0) as client:
        posted = client.post(f"{reject_provider}/action", headers=headers, json={"payload": {}})
        assert posted.status_code == 400
        body = posted.json()
        assert body["status"] == "failed"
        assert body["failure_final"] is True
        operation_id = body["operation_id"]

        status = client.get(f"{reject_provider}/operations/{operation_id}", headers=headers)
        assert status.status_code == 200
        lookup = status.json()
        assert lookup["status"] == "failed"
        assert lookup["failure_final"] is True

        counters = client.get(f"{reject_provider}/admin/counters", headers=headers).json()
        assert counters["post_count"] == 1
        assert counters["get_count"] == 1
        assert counters["effect_count"] == 0
