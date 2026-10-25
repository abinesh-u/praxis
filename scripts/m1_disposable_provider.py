#!/usr/bin/env python3
"""Run a disposable real-HTTP provider for M1 validation.

The provider is intentionally local and bounded: it stores operations only in
memory, requires a bearer token, records independent POST/GET counters, and
supports deterministic completion, pending, rejection, accepted-then-delayed
response, missing-operation-ID, and final/ambiguous failure behavior.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlparse

HOST = os.getenv("M1_PROVIDER_HOST", "127.0.0.1")
PORT = int(os.getenv("M1_PROVIDER_PORT", "8765"))
TOKEN = os.getenv("M1_PROVIDER_TOKEN", "")
MODE = os.getenv("M1_PROVIDER_MODE", "complete")
DELAY_SECONDS = float(os.getenv("M1_PROVIDER_DELAY_SECONDS", "15"))

operations: dict[str, dict[str, str | bool]] = {}
idempotency: dict[str, str] = {}
counters = {"post_count": 0, "get_count": 0, "effect_count": 0}
state_lock = Lock()


def json_bytes(document: object) -> bytes:
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


class ProviderHandler(BaseHTTPRequestHandler):
    server_version = "PraxisM1Provider/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        # Avoid writing request headers or payloads, including credentials.
        return

    def authorized(self) -> bool:
        expected = f"Bearer {TOKEN}" if TOKEN else ""
        return secrets.compare_digest(self.headers.get("Authorization", ""), expected)

    def send_json(self, status: int, document: object, *, operation_id: str | None = None) -> None:
        body = json_bytes(document)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if operation_id:
            self.send_header("X-Operation-ID", operation_id)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if not self.authorized():
            self.send_json(401, {"error": "unauthorized"})
            return
        if urlparse(self.path).path != "/action":
            self.send_json(404, {"error": "not_found"})
            return
        with state_lock:
            counters["post_count"] += 1
            key = self.headers.get("Idempotency-Key", "")
            if not key:
                self.send_json(400, {"error": "missing_idempotency_key"})
                return
            operation_id = idempotency.get(key)
            is_new = operation_id is None
            if operation_id is None:
                operation_id = f"op-{secrets.token_hex(8)}"
                idempotency[key] = operation_id
                operations[operation_id] = {"status": "pending", "idempotency_key": key}
                if MODE == "complete":
                    operations[operation_id]["status"] = "completed"
                elif MODE == "reject":
                    operations[operation_id]["status"] = "failed"
                    operations[operation_id]["failure_final"] = True
                if MODE != "reject":
                    counters["effect_count"] += 1
            stored = operations[operation_id]
            status = stored["status"]
            failure_final = stored.get("failure_final") is True

        if failure_final:
            self.send_json(
                400,
                {
                    "operation_id": operation_id,
                    "status": "failed",
                    "failure_final": True,
                },
                operation_id=operation_id,
            )
            return
        if MODE == "missing_id" and is_new:
            self.send_json(200, {"status": status})
            return
        if MODE == "timeout_after_acceptance" and is_new:
            body = json_bytes({"operation_id": operation_id, "status": status})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Operation-ID", operation_id)
            self.end_headers()
            self.wfile.flush()
            time.sleep(DELAY_SECONDS)
            if MODE == "timeout_after_acceptance":
                with state_lock:
                    operations[operation_id]["status"] = "completed"
            with suppress(BrokenPipeError):
                self.wfile.write(body)
            return
        self.send_json(
            200,
            {"operation_id": operation_id, "status": status},
            operation_id=operation_id,
        )

    def do_GET(self) -> None:  # noqa: N802
        if not self.authorized():
            self.send_json(401, {"error": "unauthorized"})
            return
        path = urlparse(self.path).path
        if path == "/admin/counters":
            with state_lock:
                self.send_json(200, dict(counters))
            return
        prefix = "/operations/"
        if not path.startswith(prefix):
            self.send_json(404, {"error": "not_found"})
            return
        operation_id = path.removeprefix(prefix)
        with state_lock:
            counters["get_count"] += 1
            operation = operations.get(operation_id)
            if operation is None:
                self.send_json(404, {"status": "failed", "failure_final": True})
                return
            if MODE == "final_failure":
                self.send_json(
                    200,
                    {
                        "operation_id": operation_id,
                        "status": "failed",
                        "failure_final": True,
                    },
                    operation_id=operation_id,
                )
                return
            if MODE == "ambiguous_failure":
                self.send_json(
                    200,
                    {"operation_id": operation_id, "status": "failed"},
                    operation_id=operation_id,
                )
                return
            document: dict[str, str | bool] = {
                "operation_id": operation_id,
                "status": str(operation["status"]),
            }
            if operation.get("failure_final") is True:
                document["failure_final"] = True
            self.send_json(200, document, operation_id=operation_id)


def main() -> int:
    if not TOKEN:
        print("Set M1_PROVIDER_TOKEN to a disposable bearer token.", file=sys.stderr)
        return 2
    if MODE not in {
        "complete",
        "pending",
        "reject",
        "timeout_after_acceptance",
        "missing_id",
        "final_failure",
        "ambiguous_failure",
    }:
        print(f"Unsupported M1_PROVIDER_MODE: {MODE}", file=sys.stderr)
        return 2
    server = ThreadingHTTPServer((HOST, PORT), ProviderHandler)
    print(f"M1 provider listening at http://{HOST}:{PORT}")
    print(f"Configure Praxis with PRAXIS_WEBHOOK_URL=http://{HOST}:{PORT}/action")
    print(f"Configure PRAXIS_WEBHOOK_STATUS_URL=http://{HOST}:{PORT}/operations")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
