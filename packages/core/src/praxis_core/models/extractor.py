"""Nebius-backed TaskExtractor adapter converting conversational input to structured tasks."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from praxis_core.entities.common import Priority
from praxis_core.models.config import ModelProfile
from praxis_core.models.providers.nebius import NebiusTokenFactoryAdapter
from praxis_core.models.registry import ModelRegistry
from praxis_core.models.router import ModelRouter
from praxis_core.ports.task_extractor import ExtractedTaskData, TaskExtractor

logger = logging.getLogger(__name__)

VAGUE_PATTERNS = {
    "do it",
    "do that",
    "fix it",
    "check this",
    "handle it",
    "work on stuff",
    "do stuff",
    "todo",
}

EXTRACTION_SYSTEM_PROMPT = """You are Praxis's task extraction engine.
Convert the user's conversational commitment into a structured JSON task specification.

Rules:
1. Identify the core obligation into a clear, concise 'title'.
2. Identify the single smallest, immediate physical next step into 'next_action_description'.
3. Resolve relative dates (e.g., 'tomorrow 5pm', 'by Friday') using the reference time and timezone.
4. Output dates in ISO 8601 format with timezone offset (e.g. 2026-10-23T17:00:00Z) or null.
5. If input is fundamentally ambiguous, missing critical info, or too vague to act on,
   set 'clarification_needed' to true and provide a helpful 'clarification_prompt'.
6. Output ONLY valid JSON matching this schema:
{
  "title": string,
  "description": string,
  "priority": "routine" | "important" | "urgent",
  "due_date": string or null,
  "scheduled_date": string or null,
  "next_action_description": string,
  "suggested_tool_hint": string or null,
  "suggested_tool_args": object,
  "clarification_needed": boolean,
  "clarification_prompt": string or null
}
"""


class NebiusTaskExtractor(TaskExtractor):
    """Task extractor utilizing Nebius Token Factory via ModelRouter."""

    def __init__(
        self,
        router: ModelRouter | None = None,
        profile: ModelProfile = ModelProfile.ROUTINE_TASKS,
        mock_provider: Any = None,
        api_key: str | None = None,
    ) -> None:
        self.router = router
        self.profile = profile
        self.mock_provider = mock_provider
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY", "")

    async def extract(
        self,
        text: str,
        reference_time: datetime,
        user_timezone: str = "UTC",
    ) -> ExtractedTaskData:
        clean_text = text.strip()

        # Heuristic check for trivially vague input
        if len(clean_text) < 4 or clean_text.lower() in VAGUE_PATTERNS:
            return ExtractedTaskData(
                title=clean_text or "Unspecified commitment",
                description=clean_text,
                clarification_needed=True,
                clarification_prompt="Could you clarify what specific task needs to be completed?",
            )

        context_prompt = (
            f"Reference Time: {reference_time.isoformat()}\n"
            f"User Timezone: {user_timezone}\n"
            f"User Commitment: {clean_text}"
        )

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": context_prompt},
        ]

        raw_response: str | None = None
        try:
            if self.mock_provider is not None:
                if callable(self.mock_provider):
                    raw_response = await self.mock_provider(messages)
                else:
                    raw_response = str(self.mock_provider)
            elif not self.api_key:
                return self._deterministic_fallback(clean_text)
            else:
                router = self.router or ModelRouter(registry=ModelRegistry())
                model_config = router.resolve_model_for_profile(self.profile.value)
                adapter = NebiusTokenFactoryAdapter(
                    config=model_config,
                    api_key=self.api_key,
                )
                raw_response = adapter.chat(messages)
        except Exception as exc:
            logger.warning("Extraction model inference failed: %s. Using fallback.", exc)
            return self._deterministic_fallback(clean_text)

        if not raw_response:
            return self._deterministic_fallback(clean_text)

        return self._parse_json_response(raw_response, clean_text)

    def _parse_json_response(self, raw_response: str, fallback_text: str) -> ExtractedTaskData:
        """Parse model response into typed ExtractedTaskData."""
        text = raw_response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    return self._deterministic_fallback(fallback_text)
            else:
                return self._deterministic_fallback(fallback_text)

        due_date = self._parse_iso_date(data.get("due_date"))
        scheduled_date = self._parse_iso_date(data.get("scheduled_date"))

        priority_str = str(data.get("priority", "routine")).lower()
        priority = Priority.ROUTINE
        if priority_str == "important":
            priority = Priority.IMPORTANT
        elif priority_str == "urgent":
            priority = Priority.URGENT

        return ExtractedTaskData(
            title=data.get("title") or fallback_text[:60],
            description=data.get("description", ""),
            priority=priority,
            due_date=due_date,
            scheduled_date=scheduled_date,
            next_action_description=data.get("next_action_description") or "Take the first step",
            suggested_tool_hint=data.get("suggested_tool_hint"),
            suggested_tool_args=data.get("suggested_tool_args") or {},
            clarification_needed=bool(data.get("clarification_needed", False)),
            clarification_prompt=data.get("clarification_prompt"),
        )

    @staticmethod
    def _parse_iso_date(val: Any) -> datetime | None:
        if not val or not isinstance(val, str):
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _deterministic_fallback(text: str) -> ExtractedTaskData:
        """Safe fallback when model fails or is offline."""
        title = text[:60] if len(text) > 60 else text
        return ExtractedTaskData(
            title=title,
            description=text,
            priority=Priority.ROUTINE,
            next_action_description="Review commitment and identify first step",
        )
