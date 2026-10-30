"""Unit tests for TavilySearchTool in bounded agent runtime."""

from __future__ import annotations

import httpx
from praxis_agent_runtime.tools.builtin.tavily_search import (
    TavilySearchArgs,
    TavilySearchTool,
)
from praxis_agent_runtime.types import ActionRiskLevel


def test_tavily_tool_metadata():
    tool = TavilySearchTool()
    assert tool.name == "tavily_search"
    assert tool.risk_level == ActionRiskLevel.READ_ONLY
    assert not tool.requires_approval
    assert tool.args_schema is TavilySearchArgs


def test_tavily_args_validation():
    args = TavilySearchArgs(query="NVIDIA Nemotron 3.5 Lightning")
    assert args.query == "NVIDIA Nemotron 3.5 Lightning"
    assert args.max_results == 5
    assert args.search_depth == "basic"
    assert args.include_answer is True


def test_tavily_offline_preview_without_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tool = TavilySearchTool()

    res = tool.run({"query": "Nebius Token Factory documentation"})
    assert res.success is True
    assert "[Tavily Search Offline Preview]" in res.output
    assert res.evidence["query"] == "Nebius Token Factory documentation"
    assert res.evidence["offline_fallback"] is True


def test_tavily_successful_mock_http_response():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.tavily.com/search"
        data = {
            "answer": "Nebius Token Factory provides high-throughput inference for NVIDIA models.",
            "results": [
                {
                    "title": "Nebius Token Factory Docs",
                    "url": "https://docs.nebius.com/token-factory",
                    "content": "API documentation and quickstart guides for Nemotron models.",
                },
                {
                    "title": "NVIDIA Nemotron Overview",
                    "url": "https://build.nvidia.com/nvidia/nemotron",
                    "content": "State-of-the-art open-source foundation models.",
                },
            ],
        }
        return httpx.Response(200, json=data)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    tool = TavilySearchTool(api_key="tvly-test-key", client=client)

    res = tool.run({"query": "What is Nebius Token Factory?"})
    assert res.success is True
    assert "Nebius Token Factory provides high-throughput inference" in res.output
    assert "Nebius Token Factory Docs (https://docs.nebius.com/token-factory)" in res.output
    assert res.evidence["results_count"] == 2
    assert "https://docs.nebius.com/token-factory" in res.evidence["urls"]
    assert res.evidence["has_answer"] is True


def test_tavily_http_error_handling():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized: Invalid API key")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    tool = TavilySearchTool(api_key="tvly-invalid", client=client)

    res = tool.run({"query": "test query"})
    assert res.success is False
    assert "Tavily API error HTTP 401" in res.error


def test_tavily_timeout_handling():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    tool = TavilySearchTool(api_key="tvly-test-key", client=client)

    res = tool.run({"query": "slow query"})
    assert res.success is False
    assert "timed out" in res.error
