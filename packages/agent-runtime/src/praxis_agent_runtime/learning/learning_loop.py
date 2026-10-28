"""Learning loop module reviewing completed execution attempts to distill candidate skills.

Treats extracted workflows as untrusted candidates across the validation seam to prevent
prompt injection depth attacks. Extracted candidate skills are isolated from active
prompt depth until validated.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from praxis_agent_runtime.skills.models import Skill
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.types import ExecutionStatus, RunRecord

logger = logging.getLogger(__name__)

MIN_TOOL_CALLS_FOR_SKILL = 3


def sanitize_skill_content(text: str) -> str:
    """Sanitize untrusted text to prevent prompt injection and control tag escape."""
    sanitized = text.replace("<tool_call>", "").replace("</tool_call>", "")
    sanitized = sanitized.replace("<tool_response>", "").replace("</tool_response>", "")
    sanitized = sanitized.replace("```", "'''")
    return sanitized.strip()


def evaluate_run(run: RunRecord) -> Skill | None:
    """Analyze a completed run and extract an untrusted candidate skill across the seam."""
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

    sanitized_goal = sanitize_skill_content(run.goal)
    instructions_lines = [f"## Candidate Workflow (learned {datetime.now(UTC).date()})", ""]
    for i, step in enumerate(tool_steps, 1):
        args_items = []
        for k, v in (step.tool_args or {}).items():
            clean_val = sanitize_skill_content(str(v))
            args_items.append(f"{k}={clean_val!r}")
        args_summary = ", ".join(args_items)
        clean_tool = sanitize_skill_content(step.tool_name or "")
        instructions_lines.append(f"{i}. Call `{clean_tool}({args_summary})`")

    instructions_lines.append("")
    instructions_lines.append(f'*Candidate extracted from goal: "{sanitized_goal}"*')

    triggers = _extract_keywords(sanitized_goal)
    skill_name = f"candidate_{run.run_id[:8]}"

    provenance = {
        "run_id": run.run_id,
        "source_goal": sanitized_goal,
        "extracted_at": datetime.now(UTC).isoformat(),
        "tool_steps_count": len(tool_steps),
    }

    return Skill(
        name=skill_name,
        description=f"Untrusted candidate workflow learned from: {sanitized_goal[:100]}",
        triggers=triggers,
        required_tools=unique_tools,
        instructions="\n".join(instructions_lines),
        status="candidate",
        provenance=provenance,
    )


def run_learning_loop(run: RunRecord, skill_store: SkillStore) -> Skill | None:
    """Execute learning loop module, saving extracted skills as untrusted candidates."""
    skill = evaluate_run(run)
    if skill is None:
        logger.debug("Run %s did not produce a learnable skill", run.run_id)
        return None

    path = skill_store.save(skill)
    logger.info("Extracted candidate skill '%s' saved to %s (status: candidate)", skill.name, path)
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
