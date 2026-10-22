"""Nebius Token Factory provider adapter."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from praxis_core.models.config import ModelConfig
from praxis_core.models.providers.base import (
    NormalizedCompletionRequest,
    NormalizedCompletionResponse,
    ProviderAdapter,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base exception for provider errors."""


class AuthenticationError(ProviderError):
    """Invalid or missing API key."""


class RateLimitError(ProviderError):
    """Provider rate limit reached."""


class ModelUnavailableError(ProviderError):
    """Model or provider endpoint is temporarily unavailable."""


class TimeoutError(ProviderError):
    """Request exceeded configured timeout."""


class InvalidResponseError(ProviderError):
    """Provider returned malformed or unexpected response format."""


class NebiusTokenFactoryAdapter(ProviderAdapter):
    """Adapter for Nebius Token Factory API (OpenAI-compatible)."""

    def __init__(
        self,
        config: ModelConfig,
        api_key: str,
        base_url: str = "https://api.tokenfactory.nebius.com/v1",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = http_client

    def _redact(self, message: str) -> str:
        """Ensure secrets are never present in error messages or logs."""
        if self._api_key and self._api_key in message:
            return message.replace(self._api_key, "[REDACTED_API_KEY]")
        return message

    def invoke(self, request: NormalizedCompletionRequest) -> NormalizedCompletionResponse:
        """Invoke Nebius Token Factory completion endpoint."""
        if not self._api_key:
            raise AuthenticationError("Nebius API key is not configured")

        if not self.config.enabled:
            raise ModelUnavailableError(f"Model '{self.config.key}' is currently disabled")

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        temperature = (
            request.temperature if request.temperature is not None else self.config.temperature
        )
        max_tokens = (
            request.max_tokens if request.max_tokens is not None else self.config.max_output_tokens
        )
        timeout = (
            request.timeout_seconds
            if request.timeout_seconds is not None
            else self.config.timeout_seconds
        )

        payload: dict[str, Any] = {
            "model": self.config.model_id,
            "messages": request.messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        start_time = time.monotonic()
        client = self._client or httpx.Client()
        should_close = self._client is None

        try:
            response = client.post(endpoint, headers=headers, json=payload, timeout=timeout)
        except httpx.TimeoutException as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            raise TimeoutError(f"Nebius request timed out after {timeout}s: {exc}") from exc
        except httpx.RequestError as exc:
            msg = self._redact(str(exc))
            raise ProviderError(f"Nebius network connection error: {msg}") from exc
        finally:
            if should_close:
                client.close()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if response.status_code == 401 or response.status_code == 403:
            raise AuthenticationError(f"Nebius authentication failure ({response.status_code})")
        elif response.status_code == 429:
            raise RateLimitError("Nebius rate limit exceeded (429)")
        elif response.status_code >= 500:
            raise ModelUnavailableError(
                f"Nebius service unavailable ({response.status_code}): {response.text}"
            )
        elif response.status_code != 200:
            raise ProviderError(f"Nebius returned status {response.status_code}: {response.text}")

        try:
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise InvalidResponseError("No choices returned in Nebius response")

            text = choices[0].get("message", {}).get("content", "")

            raw_usage = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                completion_tokens=raw_usage.get("completion_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            )

            return NormalizedCompletionResponse(
                text=text,
                model=self.config.model_id,
                provider="nebius",
                usage=usage,
                latency_ms=elapsed_ms,
                raw_response={k: v for k, v in data.items() if k != "headers"},
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidResponseError(f"Malformed JSON from Nebius: {exc}") from exc
