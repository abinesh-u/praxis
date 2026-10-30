"""Live smoke test for Tavily AI Search with real credentials."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import pytest
from praxis_agent_runtime.tools.builtin.tavily_search import TavilySearchTool


@pytest.mark.skipif(
    not os.environ.get("TAVILY_API_KEY"),
    reason="TAVILY_API_KEY environment variable not set; skipping live smoke test",
)
def test_live_tavily_search_smoke():
    api_key = os.environ["TAVILY_API_KEY"]
    tool = TavilySearchTool(api_key=api_key)

    res = tool.run({"query": "Nebius Token Factory NVIDIA Nemotron", "max_results": 3})

    assert res.success is True
    assert res.evidence["results_count"] > 0
    assert len(res.evidence["urls"]) > 0
    assert res.duration_ms is not None and res.duration_ms > 0
