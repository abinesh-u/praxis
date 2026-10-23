"""Small HTTP transport for the shared Praxis API.

This module deliberately contains no CLI rendering or domain decisions. It
only turns already validated CLI inputs into the stable API contract and
returns decoded API documents to the calling command layer.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from praxis_cli.config import DEFAULT_PRAXIS_API_URL, resolve_api_url


class PraxisApiError(Exception):
    """Base error for an unsuccessful Praxis API interaction."""


class PraxisApiUnavailableError(PraxisApiError):
    """Raised when the configured API cannot be contacted."""


class PraxisApiResponseError(PraxisApiError):
    """Raised when the API rejects a request or returns an invalid document."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PraxisApiClient:
    """Synchronous, injectable HTTP client for API-backed CLI workflows."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
        api_token: str | None = None,
    ) -> None:
        self.base_url = resolve_api_url(DEFAULT_PRAXIS_API_URL if base_url is None else base_url)
        self._owns_client = http_client is None
        token = api_token or os.getenv("PRAXIS_API_TOKEN")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = http_client or httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=headers
        )

    def __enter__(self) -> PraxisApiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the internally created HTTP client, if any."""
        if self._owns_client:
            self._client.close()

    def health(self) -> dict[str, Any]:
        """Return the API health response."""
        return self._request_document("GET", "/health")

    def capture(
        self,
        *,
        owner_id: str,
        raw_text: str,
        source: str = "cli",
        timezone: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Capture a natural-language commitment through the shared API."""
        payload: dict[str, Any] = {
            "owner_id": owner_id,
            "raw_text": raw_text,
            "source": source,
            "user_timezone": timezone,
        }
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        return self._request_document("POST", "/tasks", json=payload)

    def get_task(self, task_id: str, *, owner_id: str) -> dict[str, Any]:
        """Retrieve one task, scoped to its owner."""
        return self._request_document(
            "GET", f"/tasks/{self._path_component(task_id)}", params={"owner_id": owner_id}
        )

    def list_tasks(self, *, owner_id: str) -> list[dict[str, Any]]:
        """Retrieve the owner's tasks."""
        response = self._request_document("GET", "/tasks", params={"owner_id": owner_id})
        tasks = response.get("tasks")
        if not isinstance(tasks, list) or not all(isinstance(item, dict) for item in tasks):
            raise PraxisApiResponseError("Praxis API returned an unexpected task list.")
        return tasks

    def today(self, *, owner_id: str, at: datetime | str | None = None) -> dict[str, Any]:
        """Retrieve the owner's daily agenda at an optional explicit instant."""
        params: dict[str, str] = {"owner_id": owner_id}
        if at is not None:
            params["at"] = at.isoformat() if isinstance(at, datetime) else at
        return self._request_document("GET", "/tasks/today", params=params)

    def complete_task(
        self, task_id: str, *, owner_id: str, note: str | None = None
    ) -> dict[str, Any]:
        """Record human-confirmed completion evidence for a task."""
        payload: dict[str, Any] = {
            "owner_id": owner_id,
            "confirmation_note": note or "Verified completion by user via CLI.",
        }
        return self._request_document(
            "POST", f"/tasks/{self._path_component(task_id)}/complete", json=payload
        )

    def execute_task(
        self,
        task_id: str,
        *,
        owner_id: str,
        idempotency_key: str,
        approval_token: str | None = None,
    ) -> dict[str, Any]:
        """Request one bounded API-backed execution attempt."""
        payload: dict[str, Any] = {
            "owner_id": owner_id,
            "idempotency_key": idempotency_key,
        }
        if approval_token:
            payload["approval_token"] = approval_token
        return self._request_document(
            "POST", f"/tasks/{self._path_component(task_id)}/execute", json=payload
        )

    def reconcile_task(
        self,
        task_id: str,
        *,
        owner_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        """Read-only reconcile one uncertain execution attempt through the API.

        Reconciliation is intentionally separate from ``execute_task``.  The
        API contract performs a provider status read and never dispatches the
        original action again, so callers can safely offer this as the next
        step after an ``outcome_unknown`` response.
        """
        if not attempt_id:
            raise ValueError("Execution attempt ID must not be empty.")
        payload = {"owner_id": owner_id, "attempt_id": attempt_id}
        return self._request_document(
            "POST", f"/tasks/{self._path_component(task_id)}/reconcile", json=payload
        )

    @staticmethod
    def _path_component(value: str) -> str:
        if not value:
            raise ValueError("Task ID must not be empty.")
        return quote(value, safe="")

    def _request_document(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        data = self._request_json(method, path, **kwargs)
        if not isinstance(data, dict):
            raise PraxisApiResponseError("Praxis API returned an unexpected response document.")
        return data

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise PraxisApiUnavailableError("Unable to reach the Praxis API.") from exc

        if response.is_error:
            raise PraxisApiResponseError(
                self._error_message(response), status_code=response.status_code
            )
        try:
            return response.json()
        except ValueError as exc:
            raise PraxisApiResponseError("Praxis API returned invalid JSON.") from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        detail: object | None = None
        try:
            body = response.json()
            if isinstance(body, Mapping):
                detail = body.get("detail")
        except ValueError:
            pass
        if isinstance(detail, str) and detail:
            return f"Praxis API request failed ({response.status_code}): {detail}"
        return f"Praxis API request failed ({response.status_code})."
