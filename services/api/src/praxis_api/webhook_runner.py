"""Bounded HTTP execution adapter for the first real Praxis integration.

The configured endpoint is an explicit provider contract: POST accepts an
idempotency key and returns JSON containing ``operation_id`` and ``status``.
Only a provider-confirmed ``completed`` response is treated as success.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
from typing import Any
from urllib.parse import quote, urlparse
from uuid import UUID

import httpx
from praxis_core.entities.approval import ActionSpecification
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.next_action import NextAction
from praxis_core.entities.task import Task
from praxis_core.ports.agent_runner import AgentRunOutcome


class WebhookRunner:
    """Execute only the explicitly configured ``webhook_post`` action."""

    def __init__(
        self,
        endpoint: str | None = None,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint or os.getenv("PRAXIS_WEBHOOK_URL")
        self.timeout = timeout
        self.max_response_bytes = 1_048_576
        self.transport = transport

    @staticmethod
    def _validate_destination(url: str | None) -> str | None:
        if not url:
            return "Webhook destination is not configured"
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "Webhook destination must be an http(s) URL"
        if parsed.username or parsed.password:
            return "Webhook destination must not contain credentials"
        host = parsed.hostname.lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if host in {"localhost", "localhost.localdomain"} or (
            address and (address.is_private or address.is_loopback or address.is_link_local)
        ):
            return "Webhook destination points to a restricted private address"
        configured_hosts = os.getenv("PRAXIS_WEBHOOK_ALLOWED_HOSTS")
        if configured_hosts:
            allowed = {item.strip().lower() for item in configured_hosts.split(",") if item.strip()}
            if host not in allowed:
                return "Webhook destination host is not allowlisted"
        return None

    def _destination_error(self) -> str | None:
        return self._validate_destination(self.endpoint)

    async def _resolved_destination_error(self, url: str) -> str | None:
        parsed = urlparse(url)
        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo, parsed.hostname, parsed.port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            return f"Webhook destination could not be resolved: {exc}"
        for value in {info[4][0] for info in infos}:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if address.is_private or address.is_loopback or address.is_link_local:
                return "Webhook destination resolved to a restricted private address"
        return None

    async def _read_json(
        self, response: httpx.Response
    ) -> tuple[dict[str, Any] | None, str | None]:
        size = 0
        chunks: list[bytes] = []
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.max_response_bytes:
                return None, "Provider response exceeded size limit"
            chunks.append(chunk)
        try:
            document = json.loads(b"".join(chunks))
        except (ValueError, TypeError):
            return None, "Provider returned invalid JSON"
        if not isinstance(document, dict):
            return None, "Provider returned a non-object JSON response"
        return document, None

    async def execute_action(
        self,
        attempt_id: UUID,
        task: Task,
        action: NextAction,
        owner_id: str,
        workspace_root: str | None = None,
        approval_token: str | None = None,
    ) -> AgentRunOutcome:
        del owner_id, workspace_root
        if action.tool_hint != "webhook_post":
            return AgentRunOutcome(status="failed", error="Only webhook_post is executable")
        if not approval_token:
            return AgentRunOutcome(
                status="awaiting_approval",
                action_spec=ActionSpecification(
                    tool_name="webhook_post",
                    canonical_args=action.tool_args_hint or {"description": action.description},
                    task_id=task.id,
                    permission_scope="external_http",
                ),
                approval_justification="External webhook dispatch requires approval",
            )
        destination_error = self._destination_error()
        if destination_error:
            return AgentRunOutcome(status="failed", error=destination_error)
        resolved_error = await self._resolved_destination_error(self.endpoint)
        if resolved_error:
            return AgentRunOutcome(status="outcome_unknown", error=resolved_error)
        payload: dict[str, Any] = action.tool_args_hint or {"description": action.description}
        provider_request_id: str | None = None
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=False,
                    transport=self.transport,
                ) as client,
                client.stream(
                    "POST",
                    self.endpoint,
                    json={
                        "task_id": str(task.id),
                        "attempt_id": str(attempt_id),
                        "payload": payload,
                    },
                    headers={"Idempotency-Key": str(attempt_id)},
                ) as response,
            ):
                provider_request_id = response.headers.get("X-Operation-ID")
                document, parse_error = await self._read_json(response)
                status_code = response.status_code
        except httpx.TimeoutException:
            return AgentRunOutcome(
                status="outcome_unknown",
                error="Provider timeout after dispatch; reconcile before retrying",
                provider_request_id=provider_request_id,
            )
        except httpx.HTTPError as exc:
            return AgentRunOutcome(
                status="outcome_unknown",
                error=f"Provider request failed after dispatch; reconcile before retrying: {exc}",
                provider_request_id=provider_request_id,
            )

        if parse_error or document is None:
            return AgentRunOutcome(
                status="outcome_unknown",
                error=f"{parse_error}; reconcile before retrying",
            )
        operation_id = document.get("operation_id")
        provider_status = document.get("status")
        if status_code >= 500:
            return AgentRunOutcome(
                status="outcome_unknown",
                error=f"Provider HTTP {response.status_code}; reconcile before retrying",
            )
        if provider_status == "completed":
            evidence = Evidence.machine_verified(
                target_task_id=task.id,
                target_action_id=action.id,
                target_run_id=str(attempt_id),
                verifier_identity="integration:webhook_post",
                details={"provider": document, "http_status": status_code},
            )
            return AgentRunOutcome(
                status="completed",
                evidence=evidence,
                output=document,
                provider_request_id=str(operation_id) if operation_id else None,
            )
        return AgentRunOutcome(
            status="outcome_unknown",
            error="Provider accepted or partially processed the request; reconcile before retrying",
            output=document,
            provider_request_id=str(operation_id) if operation_id else None,
        )

    async def reconcile_action(
        self,
        attempt_id: UUID,
        task: Task,
        action: NextAction,
        owner_id: str,
        provider_request_id: str | None,
        idempotency_key: str,
    ) -> AgentRunOutcome:
        """Read provider operation state without issuing another POST."""
        del attempt_id, owner_id, action
        destination_error = self._destination_error()
        if destination_error:
            return AgentRunOutcome(status="outcome_unknown", error=destination_error)
        if not provider_request_id:
            return AgentRunOutcome(
                status="outcome_unknown",
                error="Provider operation identifier is unavailable for reconciliation",
                provider_request_id=provider_request_id,
            )
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", provider_request_id):
            return AgentRunOutcome(
                status="outcome_unknown",
                error="Provider operation identifier is invalid for status lookup",
            )
        status_endpoint = os.getenv("PRAXIS_WEBHOOK_STATUS_URL")
        status_error = self._validate_destination(status_endpoint) if status_endpoint else None
        if status_error:
            return AgentRunOutcome(status="outcome_unknown", error=status_error)
        if status_endpoint:
            url = status_endpoint.rstrip("/") + "/" + quote(provider_request_id, safe="")
        else:
            url = self.endpoint.rstrip("/") + "/operations/" + quote(provider_request_id, safe="")
        resolved_error = await self._resolved_destination_error(url)
        if resolved_error:
            return AgentRunOutcome(status="outcome_unknown", error=resolved_error)
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=False,
                    transport=self.transport,
                ) as client,
                client.stream("GET", url, headers={"Idempotency-Key": idempotency_key}) as response,
            ):
                document, parse_error = await self._read_json(response)
                status_code = response.status_code
        except httpx.TimeoutException:
            return AgentRunOutcome(
                status="outcome_unknown",
                error="Provider status lookup timed out",
                provider_request_id=provider_request_id,
            )
        except httpx.HTTPError as exc:
            return AgentRunOutcome(status="failed", error=f"Provider status lookup failed: {exc}")
        if parse_error or document is None:
            return AgentRunOutcome(
                status="outcome_unknown", error=parse_error or "Provider status was not JSON"
            )
        provider_status = document.get("status")
        if provider_status == "completed":
            return AgentRunOutcome(
                status="completed",
                evidence=Evidence.machine_verified(
                    target_task_id=task.id,
                    verifier_identity="integration:webhook_post.reconcile",
                    details={"provider": document, "http_status": status_code},
                ),
                output=document,
                provider_request_id=provider_request_id,
            )
        if provider_status == "failed" and document.get("failure_final") is True:
            return AgentRunOutcome(
                status="failed",
                error=document.get("error") or "Provider reported operation failure",
                output=document,
                provider_request_id=provider_request_id,
            )
        return AgentRunOutcome(
            status="outcome_unknown",
            error="Provider operation remains pending or unconfirmed",
            output=document,
            provider_request_id=provider_request_id,
        )
