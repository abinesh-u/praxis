"""Unit tests for NebiusTokenFactoryAdapter."""

import httpx
import pytest
from praxis_core.models.config import ModelConfig
from praxis_core.models.providers.base import NormalizedCompletionRequest
from praxis_core.models.providers.nebius import (
    AuthenticationError,
    ModelUnavailableError,
    NebiusTokenFactoryAdapter,
    RateLimitError,
    TimeoutError,
)


def _sample_config(enabled: bool = True) -> ModelConfig:
    return ModelConfig(
        key="nemotron-test",
        display_name="Nemotron Test",
        provider="nebius",
        model_id="nvidia/Nemotron-3_5-Lightning",
        enabled=enabled,
    )


class TestNebiusTokenFactoryAdapter:
    def test_missing_api_key_raises(self):
        adapter = NebiusTokenFactoryAdapter(config=_sample_config(), api_key="")
        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hi"}])
        with pytest.raises(AuthenticationError, match="not configured"):
            adapter.invoke(req)

    def test_disabled_model_raises(self):
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(enabled=False),
            api_key="dummy_key",
        )
        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hi"}])
        with pytest.raises(ModelUnavailableError, match="disabled"):
            adapter.invoke(req)

    def test_successful_invocation_with_mock_client(self):
        mock_response = {
            "id": "chatcmpl-123",
            "choices": [{"message": {"content": "Hello there!"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        def mock_handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer test_secret_key"
            return httpx.Response(200, json=mock_response)

        mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(),
            api_key="test_secret_key",
            http_client=mock_client,
        )

        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hello"}])
        resp = adapter.invoke(req)

        assert resp.text == "Hello there!"
        assert resp.model == "nvidia/Nemotron-3_5-Lightning"
        assert resp.usage.total_tokens == 15
        assert resp.provider == "nebius"

    def test_authentication_error(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(),
            api_key="bad_key",
            http_client=mock_client,
        )

        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hi"}])
        with pytest.raises(AuthenticationError):
            adapter.invoke(req)

    def test_rate_limit_error(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "rate limit"})

        mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(),
            api_key="key",
            http_client=mock_client,
        )

        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hi"}])
        with pytest.raises(RateLimitError):
            adapter.invoke(req)

    def test_timeout_error(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("Connection timed out")

        mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(),
            api_key="key",
            http_client=mock_client,
        )

        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hi"}])
        with pytest.raises(TimeoutError):
            adapter.invoke(req)

    def test_secret_redaction_in_errors(self):
        secret = "secret_super_api_token_12345"

        def mock_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"Failed to connect using token {secret}")

        mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(),
            api_key=secret,
            http_client=mock_client,
        )

        req = NormalizedCompletionRequest(messages=[{"role": "user", "content": "hi"}])
        try:
            adapter.invoke(req)
        except Exception as exc:
            assert secret not in str(exc)
            assert "[REDACTED_API_KEY]" in str(exc)

    def test_chat_protocol_method(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "protocol ok"}}]})

        mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
        adapter = NebiusTokenFactoryAdapter(
            config=_sample_config(),
            api_key="test_key",
            http_client=mock_client,
        )
        result = adapter.chat([{"role": "user", "content": "hi"}])
        assert result == "protocol ok"
