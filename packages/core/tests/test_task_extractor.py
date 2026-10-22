"""Unit tests for NebiusTaskExtractor adapter and JSON parsing."""

import json
from datetime import UTC, datetime

import pytest
from praxis_core.entities.common import Priority
from praxis_core.models.extractor import NebiusTaskExtractor


class TestNebiusTaskExtractor:
    """Verifies prompt building, JSON repair, date parsing, and fallback behaviors."""

    @pytest.mark.anyio
    async def test_extract_valid_json_response(self):
        sample_json = {
            "title": "Clean out Docker volumes",
            "description": "Reclaim disk space",
            "priority": "important",
            "due_date": "2026-10-23T17:00:00Z",
            "scheduled_date": None,
            "next_action_description": "Run docker system df to inspect disk space",
            "suggested_tool_hint": "shell_run",
            "suggested_tool_args": {"command": "docker system df"},
            "clarification_needed": False,
            "clarification_prompt": None,
        }

        async def mock_provider(messages):
            return json.dumps(sample_json)

        extractor = NebiusTaskExtractor(mock_provider=mock_provider)
        ref_time = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)

        result = await extractor.extract(
            text="Need to clean out Docker volumes by tomorrow 5pm",
            reference_time=ref_time,
            user_timezone="UTC",
        )

        assert result.title == "Clean out Docker volumes"
        assert result.priority == Priority.IMPORTANT
        assert result.due_date == datetime(2026, 10, 23, 17, 0, 0, tzinfo=UTC)
        assert result.next_action_description == "Run docker system df to inspect disk space"
        assert result.suggested_tool_hint == "shell_run"
        assert result.clarification_needed is False

    @pytest.mark.anyio
    async def test_extract_markdown_fenced_json(self):
        fenced_content = """```json
{
  "title": "Review pull request #12",
  "description": "Check review comments",
  "priority": "routine",
  "due_date": null,
  "scheduled_date": null,
  "next_action_description": "Open PR in browser and inspect diff",
  "suggested_tool_hint": null,
  "suggested_tool_args": {},
  "clarification_needed": false,
  "clarification_prompt": null
}
```"""
        extractor = NebiusTaskExtractor(mock_provider=fenced_content)
        result = await extractor.extract(
            text="Review PR 12",
            reference_time=datetime.now(UTC),
        )

        assert result.title == "Review pull request #12"
        assert result.priority == Priority.ROUTINE
        assert result.next_action_description == "Open PR in browser and inspect diff"

    @pytest.mark.anyio
    async def test_vague_input_triggers_clarification_heuristic(self):
        extractor = NebiusTaskExtractor()
        result = await extractor.extract(
            text="do it",
            reference_time=datetime.now(UTC),
        )

        assert result.clarification_needed is True
        assert result.clarification_prompt is not None

    @pytest.mark.anyio
    async def test_malformed_model_output_uses_safe_fallback(self):
        extractor = NebiusTaskExtractor(
            mock_provider="I am an AI and cannot generate JSON right now.",
        )
        result = await extractor.extract(
            text="Backup postgres database to S3",
            reference_time=datetime.now(UTC),
        )

        # Fallback uses input text without crashing
        assert "Backup postgres database to S3" in result.title
        assert result.clarification_needed is False
        assert result.next_action_description is not None
