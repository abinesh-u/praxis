"""Skill Matcher module — selects relevant validated skills based on user task description.

Preserves prompt depth and execution safety by strictly matching validated skills
and quarantining untrusted candidate skills across the seam.
"""

from __future__ import annotations

from praxis_agent_runtime.skills.models import Skill


def match_skills(
    goal: str,
    skills: list[Skill],
    max_results: int = 3,
) -> list[Skill]:
    """Return the most relevant validated skills for a given goal, ranked by keyword overlap."""
    goal_words = set(goal.lower().split())
    scored: list[tuple[int, Skill]] = []

    for skill in skills:
        # Strict quarantine: untrusted candidates must never enter prompt depth
        if not getattr(skill, "is_validated", True):
            continue

        trigger_words = {t.lower() for t in skill.triggers}
        overlap = len(goal_words & trigger_words)
        if overlap > 0:
            scored.append((overlap, skill))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [skill for _, skill in scored[:max_results]]
