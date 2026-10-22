"""Skill Matcher — selects relevant skills based on user task description."""

from __future__ import annotations

from praxis_agent_runtime.skills.models import Skill


def match_skills(
    goal: str,
    skills: list[Skill],
    max_results: int = 3,
) -> list[Skill]:
    """Return the most relevant skills for a given goal, ranked by keyword overlap."""
    goal_words = set(goal.lower().split())
    scored: list[tuple[int, Skill]] = []

    for skill in skills:
        trigger_words = {t.lower() for t in skill.triggers}
        overlap = len(goal_words & trigger_words)
        if overlap > 0:
            scored.append((overlap, skill))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [skill for _, skill in scored[:max_results]]
