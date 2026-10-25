#!/usr/bin/env python3
"""Run the two safe phases of M1 real-provider validation.

This script intentionally has no retry loop. Run ``dispatch`` once, preserve
the returned attempt ID, restart Praxis if required, then run ``reconcile``.
Provider-side POST/GET counters must come from the provider's own logs or test
dashboard; this script reports only Praxis responses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def api_base_url() -> str:
    value = os.getenv("PRAXIS_API_URL", "http://localhost:8000").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("PRAXIS_API_URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("PRAXIS_API_URL must not contain credentials, query, or fragment data")
    return value.rstrip("/")


def required_uuid(name: str) -> str:
    value = required(name)
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise SystemExit(f"{name} must be a UUID") from exc


def api_request(
    method: str,
    path: str,
    *,
    base_url: str,
    token: str,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(
                method,
                f"{base_url.rstrip('/')}{path}",
                json=payload,
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise SystemExit(f"Praxis API unavailable: {exc}") from exc
    try:
        document = response.json()
    except ValueError as exc:
        raise SystemExit(f"Praxis API returned invalid JSON ({response.status_code})") from exc
    if response.is_error:
        raise SystemExit(f"Praxis API rejected request ({response.status_code})")
    if not isinstance(document, dict):
        raise SystemExit("Praxis API returned a non-object response")
    return document


def safe_report(document: dict[str, Any]) -> dict[str, Any]:
    """Keep reports free of bearer tokens, idempotency keys, and raw payloads."""
    allowed = {
        "attempt_id",
        "attempt_status",
        "outcome_status",
        "provider_request_id",
        "error",
        "task",
    }
    report = {key: document[key] for key in allowed if key in document}
    task = report.get("task")
    if isinstance(task, dict):
        report["task"] = {
            key: task[key]
            for key in ("id", "title", "status", "failure_reason", "recovery_suggestion")
            if key in task
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="phase", required=True)
    dispatch = subparsers.add_parser("dispatch", help="Submit exactly one approved attempt")
    dispatch.add_argument("--idempotency-key", required=True)
    reconcile = subparsers.add_parser("reconcile", help="Perform one read-only status lookup")
    reconcile.add_argument("--attempt-id", required=True)
    args = parser.parse_args()

    base_url = api_base_url()
    api_timeout = float(os.getenv("PRAXIS_API_TIMEOUT", "30"))
    if api_timeout <= 0:
        raise SystemExit("PRAXIS_API_TIMEOUT must be greater than zero")
    owner_id = required("PRAXIS_OWNER_ID")
    token = required("PRAXIS_API_TOKEN")
    task_id = required_uuid("PRAXIS_TASK_ID")

    if args.phase == "dispatch":
        if not args.idempotency_key.strip():
            raise SystemExit("--idempotency-key must not be empty")
        document = api_request(
            "POST",
            f"/tasks/{task_id}/execute",
            base_url=base_url,
            token=token,
            payload={
                "owner_id": owner_id,
                "idempotency_key": args.idempotency_key,
                "approval_token": required("PRAXIS_APPROVAL_TOKEN"),
            },
            timeout=api_timeout,
        )
        print(json.dumps({"phase": "dispatch", **safe_report(document)}, indent=2, sort_keys=True))
        if document.get("attempt_status") == "outcome_unknown":
            print(
                "Next step: restart/review Praxis, then run reconcile with the returned "
                "attempt_id.",
                file=sys.stderr,
            )
    else:
        try:
            attempt_id = str(UUID(args.attempt_id))
        except ValueError as exc:
            raise SystemExit("--attempt-id must be a UUID") from exc
        document = api_request(
            "POST",
            f"/tasks/{task_id}/reconcile",
            base_url=base_url,
            token=token,
            payload={"owner_id": owner_id, "attempt_id": attempt_id},
            timeout=api_timeout,
        )
        print(json.dumps({"phase": "reconcile", **safe_report(document)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
