"""Tag Parser — extracts <tool_call> blocks from LLM output."""

from __future__ import annotations

import json
import re

from praxis_agent_runtime.types import ParsedToolCall

_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL,
)


def extract_tool_calls(text: str) -> tuple[str, list[ParsedToolCall]]:
    """Extract tool calls from LLM output text."""
    tool_calls: list[ParsedToolCall] = []

    for match in _TOOL_CALL_PATTERN.finditer(text):
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in <tool_call> block: {raw_json!r}") from exc

        if not isinstance(parsed, dict) or "name" not in parsed:
            raise ValueError(f"<tool_call> missing 'name' field: {parsed!r}")

        tool_calls.append(
            ParsedToolCall(
                name=parsed["name"],
                arguments=parsed.get("arguments", {}),
            )
        )

    clean_text = _TOOL_CALL_PATTERN.sub("", text).strip()
    return clean_text, tool_calls


def format_tool_response(tool_name: str, result: str) -> str:
    """Format a tool result for injection back into the LLM conversation."""
    return f'<tool_response name="{tool_name}">\n{result}\n</tool_response>'
