"""Prompt Formatter — assembles system prompt with tool definitions and skills."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praxis_agent_runtime.tools.base import BaseTool

_SYSTEM_TEMPLATE = """\
You are Praxis, a personal AI execution partner. You help the user accomplish \
real tasks — not just talk about them.

## Rules
- Execute tasks step by step. Think before each action.
- Stop after completing the goal. Do not invent extra work.
- If you are unsure or lack permission, ask the user instead of guessing.
- Never claim an action succeeded without verifiable evidence.

## Available Tools
To use a tool, emit a <tool_call> tag with a JSON object containing "name" and "arguments":

<tool_call>{{"name": "tool_name", "arguments": {{"param": "value"}}}}</tool_call>

After a tool executes, you will receive its result in a <tool_response> tag.
Only call one tool at a time. Wait for the response before calling another.

{tool_definitions}
{skill_section}\
"""


def format_tool_definitions(tools: list[BaseTool]) -> str:
    """Render all available tools as a numbered list with JSON schemas."""
    if not tools:
        return "No tools are currently available."

    lines: list[str] = ["### Tool Definitions", ""]
    for i, tool in enumerate(tools, 1):
        schema = tool.args_schema.model_json_schema() if tool.args_schema else {}
        lines.append(f"**{i}. {tool.name}** — {tool.description}")
        lines.append(f"   Risk: {tool.risk_level.value}")
        if schema:
            props = schema.get("properties", {})
            required = schema.get("required", [])
            compact = {"properties": props, "required": required}
            lines.append(f"   Parameters: {json.dumps(compact, indent=2)}")
        lines.append("")

    return "\n".join(lines)


def build_system_prompt(
    tools: list[BaseTool],
    skill_guides: list[str] | None = None,
) -> str:
    """Assemble the complete system prompt."""
    tool_defs = format_tool_definitions(tools)

    skill_section = ""
    if skill_guides:
        skill_section = "\n## Relevant Skills & Workflows\n\n"
        skill_section += "\n---\n".join(skill_guides)
        skill_section += "\n"

    return _SYSTEM_TEMPLATE.format(
        tool_definitions=tool_defs,
        skill_section=skill_section,
    )
