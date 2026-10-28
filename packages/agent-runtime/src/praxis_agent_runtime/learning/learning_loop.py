"""Learning loop module reviewing completed execution attempts to distill candidate skills.

Treats extracted workflows as untrusted candidates across the validation seam to prevent
prompt injection depth attacks. Extracted candidate skills are isolated from active
prompt depth and file locality until validated and explicitly promoted by an operator.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from praxis_agent_runtime.skills.models import Skill
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.types import ExecutionStatus, RunRecord, StepRecord

logger = logging.getLogger(__name__)

MIN_TOOL_CALLS_FOR_SKILL = 3

_INJECTION_TAGS = (
    "<tool_call>",
    "</tool_call>",
    "<tool_response>",
    "</tool_response>",
    "<system>",
    "</system>",
    "<prompt>",
    "</prompt>",
    "<user>",
    "</user>",
    "<assistant>",
    "</assistant>",
    "<control>",
    "</control>",
)


def sanitize_skill_content(text: str) -> str:
    """Sanitize untrusted text across the validation seam to prevent prompt injection.

    Neutralizes control tags, markdown block escapes, and instruction override headers.
    """
    sanitized = text
    for tag in _INJECTION_TAGS:
        sanitized = sanitized.replace(tag, "")

    # Neutralize triple backticks to prevent markdown code block breakout
    sanitized = sanitized.replace("```", "'''")

    # Neutralize malicious role injection prefixes both inline and line-based
    sanitized = re.sub(
        r"(?i)\b(system|instruction|ignore\s+previous\s+instructions)\s*:",
        "[REDACTED_DIRECTIVE: directive]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\bignore\s+previous\s+instructions\b",
        "[REDACTED_DIRECTIVE: ignore previous]",
        sanitized,
    )

    return sanitized.strip()


def evaluate_run(
    run: RunRecord,
    *,
    attempt_id: UUID | str | None = None,
    owner_id: str = "default_user",
    evidence_id: UUID | str | None = None,
    evidence_hash: str | None = None,
    task_id: UUID | str | None = None,
) -> Skill | None:
    """Analyze a completed run and extract an untrusted candidate skill across the seam.

    Enforces strict eligibility:
    - Run status must be COMPLETED.
    - Run must have no errors.
    - Tool steps count must be >= MIN_TOOL_CALLS_FOR_SKILL (3).
    - Every tool step must have a successful ToolResult.
    - Candidate identity is derived from the execution attempt to leverage idempotency.
    """
    if run.status != ExecutionStatus.COMPLETED or run.error is not None:
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

    # Derive deterministic, idempotent skill name from source execution attempt ID
    if attempt_id is not None:
        clean_attempt = str(attempt_id).replace("-", "")[:12]
        skill_name = f"candidate_att_{clean_attempt}"
    else:
        skill_name = f"candidate_{run.run_id[:8]}"

    resolved_evidence_hash = evidence_hash or (
        hashlib.sha256(f"{attempt_id}:{evidence_id}".encode()).hexdigest()[:16]
        if attempt_id and evidence_id
        else "unverified"
    )

    provenance = {
        "attempt_id": str(attempt_id) if attempt_id else run.run_id,
        "task_id": str(task_id) if task_id else None,
        "owner_id": owner_id,
        "evidence_id": str(evidence_id) if evidence_id else None,
        "evidence_hash": resolved_evidence_hash,
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


def run_learning_loop(
    run: RunRecord,
    skill_store: SkillStore,
    *,
    attempt_id: UUID | str | None = None,
    owner_id: str = "default_user",
    evidence_id: UUID | str | None = None,
    evidence_hash: str | None = None,
    task_id: UUID | str | None = None,
) -> Skill | None:
    """Execute learning loop module, saving extracted skills as untrusted candidates.

    Guarantees idempotent persistence so repeated execution replays or reconciliations
    cannot create duplicate candidate skills across the seam.
    """
    skill = evaluate_run(
        run,
        attempt_id=attempt_id,
        owner_id=owner_id,
        evidence_id=evidence_id,
        evidence_hash=evidence_hash,
        task_id=task_id,
    )
    if skill is None:
        logger.debug("Run %s did not produce a learnable candidate skill", run.run_id)
        return None

    path = skill_store.save(skill)
    logger.info("Extracted candidate skill '%s' saved to %s (status: candidate)", skill.name, path)
    return skill


class AgentSkillLearner:
    """Skill learner adapter module implementing the core SkillLearner interface.

    Bridges domain execution completion to runtime skill distillation while enforcing
    provenance validation, candidate quarantine, and tenant locality.
    """

    def __init__(self, skill_store: SkillStore) -> None:
        self.skill_store = skill_store

    def learn_from_execution(
        self,
        *,
        attempt_id: UUID,
        task_id: UUID,
        owner_id: str,
        evidence: Any,
        raw_payload: Any,
        action_description: str | None = None,
    ) -> Skill | None:
        """Evaluate a completed execution attempt to extract an isolated candidate skill.

        Validates evidence verification and payload integrity before extraction.
        """
        # Strict gate: unverified executions must never enter candidate distillation
        if evidence is None or not getattr(evidence, "is_verified", lambda: False)():
            logger.warning("Skill candidate extraction aborted: execution evidence is unverified")
            return None

        if not isinstance(raw_payload, dict):
            return None

        steps_data = raw_payload.get("steps")
        if not steps_data or not isinstance(steps_data, list):
            return None

        run_id = raw_payload.get("run_id") or str(attempt_id)
        details_dict = (
            evidence.details
            if hasattr(evidence, "details") and isinstance(evidence.details, dict)
            else {}
        )
        evidence_output = str(details_dict.get("output", ""))
        goal = (
            raw_payload.get("goal") or action_description or evidence_output or f"Action {task_id}"
        )

        try:
            steps: list[StepRecord] = [StepRecord(**s) for s in steps_data]
        except Exception as exc:
            logger.warning("Failed parsing step records for candidate distillation: %s", exc)
            return None

        run = RunRecord(
            run_id=str(run_id),
            status=ExecutionStatus.COMPLETED,
            goal=str(goal),
            steps=steps,
        )

        evidence_hash = (
            getattr(evidence, "artifact_ref", None)
            or details_dict.get("verification_hash")
            or details_dict.get("receipt_hash")
            or hashlib.sha256(f"{evidence.id}:{attempt_id}".encode()).hexdigest()[:16]
        )

        return run_learning_loop(
            run=run,
            skill_store=self.skill_store,
            attempt_id=attempt_id,
            owner_id=owner_id,
            evidence_id=evidence.id,
            evidence_hash=evidence_hash,
            task_id=task_id,
        )


def _extract_keywords(text: str) -> list[str]:
    """Extract simple alphanumeric keywords from a goal string (stopword-filtered)."""
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
    # Clean tokens: strictly alphanumeric words, length 3 to 24
    clean_text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    words = clean_text.split()
    return [w for w in words if w.isalnum() and 3 <= len(w) <= 24 and w not in stopwords]
