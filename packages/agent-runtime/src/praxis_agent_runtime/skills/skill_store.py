"""Skill Store — reads and writes skill files from disk."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from praxis_agent_runtime.skills.models import Skill

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


class SkillStore:
    """File-backed store for procedural skills."""

    def __init__(self, skills_dir: str | Path) -> None:
        self._dir = Path(skills_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> list[Skill]:
        """Load all skill files from the directory."""
        skills: list[Skill] = []
        for path in sorted(self._dir.glob("*.md")):
            skill = self._parse_file(path)
            if skill:
                skills.append(skill)
        return skills

    def save(self, skill: Skill) -> Path:
        """Write a skill to disk as a Markdown file with YAML frontmatter."""
        filename = skill.name.replace(" ", "_").lower() + ".md"
        path = self._dir / filename

        frontmatter = yaml.dump(
            {
                "name": skill.name,
                "description": skill.description,
                "triggers": skill.triggers,
                "required_tools": skill.required_tools,
            },
            default_flow_style=False,
        )

        content = f"---\n{frontmatter}---\n{skill.instructions}"
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def _parse_file(path: Path) -> Skill | None:
        """Parse a Markdown skill file."""
        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_PATTERN.match(raw)
        if not match:
            return None

        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None

        if not isinstance(meta, dict) or "name" not in meta:
            return None

        return Skill(
            name=meta["name"],
            description=meta.get("description", ""),
            triggers=meta.get("triggers", []),
            required_tools=meta.get("required_tools", []),
            instructions=match.group(2).strip(),
        )
