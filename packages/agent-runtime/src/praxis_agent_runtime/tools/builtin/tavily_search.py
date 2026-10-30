"""Tavily AI Search tool — enables agent to query external facts and web docs."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.types import ActionRiskLevel, ToolResult

logger = logging.getLogger(__name__)


class TavilySearchArgs(BaseModel):
    query: str = Field(description="Search query to execute against Tavily AI Search")
    max_results: int = Field(default=5, ge=1, le=10, description="Max search results to return")
    search_depth: Literal["basic", "advanced"] = Field(
        default="basic", description="Search depth: 'basic' for fast results, 'advanced' for deep"
    )
    include_answer: bool = Field(
        default=True, description="Whether to include Tavily's synthesized answer"
    )


class TavilySearchTool(BaseTool):
    """Tool enabling bounded agent workflows to query web knowledge via Tavily."""

    name = "tavily_search"
    description = (
        "Search the web for real-time information, documentation, and external facts "
        "using Tavily AI Search API."
    )
    risk_level = ActionRiskLevel.READ_ONLY
    args_schema = TavilySearchArgs
    timeout_seconds = 15

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.tavily.com",
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client

    def _get_api_key(self) -> str | None:
        return self._api_key or os.getenv("TAVILY_API_KEY")

    def execute(
        self,
        *,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
    ) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            # Deterministic preview / fallback when API key is not provisioned
            return ToolResult(
                success=True,
                output=(
                    f"[Tavily Search Offline Preview] Simulated search for query: '{query}'. "
                    "Configure TAVILY_API_KEY in .env for live external results."
                ),
                evidence={"query": query, "offline_fallback": True, "results_count": 0},
            )

        endpoint = f"{self._base_url}/search"
        payload: dict[str, Any] = {
            "api_key": api_key,
            "query": query,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "max_results": max_results,
        }

        try:
            if self._client is not None:
                resp = self._client.post(endpoint, json=payload, timeout=self.timeout_seconds)
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(endpoint, json=payload)

            if resp.status_code != 200:
                err_text = resp.text[:200]
                return ToolResult(
                    success=False,
                    error=f"Tavily API error HTTP {resp.status_code}: {err_text}",
                )

            data = resp.json()
            answer = data.get("answer")
            results = data.get("results", [])

            output_lines: list[str] = []
            if answer:
                output_lines.append(f"Summary Answer:\n{answer}\n")

            if results:
                output_lines.append(f"Top {len(results)} Sources:")
                for idx, r in enumerate(results, start=1):
                    title = r.get("title", "Untitled")
                    url = r.get("url", "")
                    content = r.get("content", "")[:250].strip()
                    output_lines.append(f"{idx}. {title} ({url})\n   {content}")

            formatted_output = "\n".join(output_lines) if output_lines else "No results found."

            evidence = {
                "query": query,
                "results_count": len(results),
                "urls": [r.get("url") for r in results if r.get("url")],
                "has_answer": bool(answer),
            }

            return ToolResult(success=True, output=formatted_output, evidence=evidence)

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Tavily search timed out after {self.timeout_seconds}s for query '{query}'",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Tavily search failed: {type(exc).__name__}: {exc}",
            )
