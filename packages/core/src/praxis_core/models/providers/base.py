"""Base provider interfaces and normalized request/response schemas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token consumption metadata."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class NormalizedCompletionRequest(BaseModel):
    """Normalized chat completion request."""

    messages: list[dict[str, str]]
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: int | None = None


class NormalizedCompletionResponse(BaseModel):
    """Normalized chat completion response."""

    text: str
    model: str
    provider: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = 0
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ProviderAdapter(ABC):
    """Abstract provider adapter."""

    @abstractmethod
    def invoke(self, request: NormalizedCompletionRequest) -> NormalizedCompletionResponse:
        """Invoke model completion."""
        ...

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Protocol compatibility method for agent execution loop."""
        req = NormalizedCompletionRequest(messages=messages)
        res = self.invoke(req)
        return res.text
