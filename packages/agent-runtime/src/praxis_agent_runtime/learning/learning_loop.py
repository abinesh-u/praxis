"""Learning Loop — reviews completed runs and distills reusable skills."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from praxis_agent_runtime.skills.models import Skill
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.types import ExecutionStatus, RunRecord

logger = logging.getLogger(__name__)

MIN_TOOL_CALLS_FOR_SKILL = 3


def evaluate_run(run: RunRecord) -> Skill | None:
    """Analyze a completed run and extract a reusable skill if applicable."""
    if run.status != ExecutionStatus.COMPLETED:
        return None

    tool_steps = [s for s in run.steps if s.step_type == "tool_call" and s.tool_name]
    if len(tool_steps) < MIN_TOOL_CALLS_FOR_SKILL:
        return None

    tool_results = [s for s in run.steps if s.step_type == "tool_result" and s.tool_result]
    success_count = sum(1 for r in tool_results if r.tool_result and r.tool_result.success)
    if success_count < len(tool_steps):
        return None

    tool_names = [s.tool_name for s in tool_steps if s.tool_name]
    unique_tools = list(dict.fromkeys(tool_names))

    instructions_lines = [f"## Workflow (learned {datetime.now(UTC).date()})", ""]
    for i, step in enumerate(tool_steps, 1):
        args_summary = ", ".join(f"{k}={v!r}" for k, v in (step.tool_args or {}).items())
        instructions_lines.append(f"{i}. Call `{step.tool_name}({args_summary})`")

    instructions_lines.append("")
    instructions_lines.append(f'*Learned from goal: "{run.goal}"*')

    triggers = _extract_keywords(run.goal)
    skill_name = f"learned_{run.run_id[:8]}"

    return Skill(
        name=skill_name,
        description=f"Workflow learned from: {run.goal[:100]}",
        triggers=triggers,
        required_tools=unique_tools,
        instructions="\n".join(instructions_lines),
    )


def run_learning_loop(run: RunRecord, skill_store: SkillStore) -> Skill | None:
    """Full learning loop: evaluate a run, and if a skill is found, save it."""
    skill = evaluate_run(run)
    if skill is None:
        logger.debug("Run %s did not produce a learnable skill", run.run_id)
        return None

    path = skill_store.save(skill)
    logger.info("Learned new skill '%s' saved to %s", skill.name, path)
    return skill


def _extract_keywords(text: str) -> list[str]:
    """Extract simple keywords from a goal string (stopword-filtered)."""
    stopwords = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "is",
        "are",
        "was",
        "were",
        "to",
        "of",
        "in",
        "for",
        "on",
        "it",
        "this",
        "that",
        "with",
        "from",
        "at",
        "by",
        "do",
        "my",
        "me",
        "i",
        "you",
        "we",
        "they",
        "be",
        "have",
        "has",
        "had",
        "not",
        "can",
        "will",
        "just",
        "all",
        "if",
        "so",
    }
    words = text.lower().split()
    return [w for w in words if w.isalpha() and len(w) > 2 and w not in stopwords]
