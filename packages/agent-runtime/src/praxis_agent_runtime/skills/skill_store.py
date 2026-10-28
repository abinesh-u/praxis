"""Skill store module — reads and writes procedural skills preserving file locality."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from praxis_agent_runtime.skills.models import Skill

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


class SkillStore:
    """File-backed store module managing procedural skill persistence across the validation seam.

    Loads validated skills preserving locality and prompt depth while isolating
    untrusted candidate skills from execution prompts.
    """

    def __init__(self, skills_dir: str | Path) -> None:
        self._dir = Path(skills_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def load_all(self, include_candidates: bool = False) -> list[Skill]:
        """Load skill files from the directory, defaulting to validated skills only.

        Isolates untrusted candidate skills by default to prevent injection into prompt depth.
        """
        skills: list[Skill] = []
        for path in sorted(self._dir.glob("*.md")):
            skill = self._parse_file(path)
            if skill and (include_candidates or skill.is_validated):
                skills.append(skill)
        return skills

    def load_candidates(self) -> list[Skill]:
        """Load only untrusted candidate skills awaiting validation."""
        candidates: list[Skill] = []
        for path in sorted(self._dir.glob("*.md")):
            skill = self._parse_file(path)
            if skill and skill.is_candidate:
                candidates.append(skill)
        return candidates

    def save(self, skill: Skill) -> Path:
        """Write a skill to disk as a Markdown file with YAML frontmatter."""
        filename = skill.name.replace(" ", "_").lower() + ".md"
        path = self._dir / filename

        meta_dict: dict[str, Any] = {
            "name": skill.name,
            "description": skill.description,
            "triggers": skill.triggers,
            "required_tools": skill.required_tools,
            "status": skill.status,
        }
        if skill.provenance:
            meta_dict["provenance"] = skill.provenance
        if skill.validation_notes:
            meta_dict["validation_notes"] = skill.validation_notes

        frontmatter = yaml.dump(
            meta_dict,
            default_flow_style=False,
        )

        content = f"---\n{frontmatter}---\n{skill.instructions}"
        path.write_text(content, encoding="utf-8")
        return path

    def promote_candidate(
        self,
        name: str,
        validator_identity: str,
        notes: str | None = None,
    ) -> Skill:
        """Validate an untrusted candidate skill, promoting it to active execution status."""
        target_normalized = name.replace(" ", "_").lower()
        for skill in self.load_all(include_candidates=True):
            if (
                skill.name.lower() == name.lower()
                or skill.name.replace(" ", "_").lower() == target_normalized
            ):
                skill.status = "validated"
                skill.validation_notes = notes or f"Validated by {validator_identity}"
                if skill.provenance is None:
                    skill.provenance = {}
                skill.provenance["validated_by"] = validator_identity
                self.save(skill)
                return skill
        raise ValueError(f"Candidate skill '{name}' not found for promotion")

    def reject_candidate(self, name: str, reason: str) -> Skill:
        """Reject an untrusted candidate skill, preventing promotion into prompt depth."""
        target_normalized = name.replace(" ", "_").lower()
        for skill in self.load_all(include_candidates=True):
            if (
                skill.name.lower() == name.lower()
                or skill.name.replace(" ", "_").lower() == target_normalized
            ):
                skill.status = "rejected"
                skill.validation_notes = reason
                self.save(skill)
                return skill
        raise ValueError(f"Candidate skill '{name}' not found for rejection")

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
            status=meta.get("status", "validated"),
            provenance=meta.get("provenance"),
            validation_notes=meta.get("validation_notes"),
        )
