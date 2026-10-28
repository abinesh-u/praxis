"""Skill store module — reads and writes procedural skills preserving file locality."""

from __future__ import annotations

import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from praxis_agent_runtime.skills.models import (
    InvalidStateTransitionError,
    ReviewAudit,
    Skill,
    SkillCollisionError,
    SkillSecurityError,
)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
_UNSET = object()


class SkillStore:
    """File-backed store module managing procedural skill persistence across the validation seam.

    Loads validated skills preserving locality and prompt depth while isolating
    untrusted candidate skills from execution prompts.
    Enforces collision resistance, atomic persistence, tenant locality, and concurrency safety.
    """

    def __init__(self, skills_dir: str | Path) -> None:
        self._dir = Path(skills_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._global_lock = threading.RLock()
        self._skill_locks: dict[str, threading.RLock] = {}

    def _get_skill_lock(self, normalized_name: str) -> threading.RLock:
        with self._global_lock:
            if normalized_name not in self._skill_locks:
                self._skill_locks[normalized_name] = threading.RLock()
            return self._skill_locks[normalized_name]

    def _get_path_for_name(self, name: str) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip().lower())
        if not slug:
            raise ValueError(f"Invalid skill name '{name}'")
        path = (self._dir / f"{slug}.md").resolve()
        if not path.is_relative_to(self._dir):
            raise SkillSecurityError(f"Skill name '{name}' attempts path traversal")
        return path

    def _load_raw_all(self, include_candidates: bool = True) -> list[Skill]:
        skills: list[Skill] = []
        for path in sorted(self._dir.glob("*.md")):
            if path.name.startswith("."):
                continue
            skill = self._parse_file(path)
            if skill and (include_candidates or skill.is_validated):
                skills.append(skill)
        return skills

    def load_all(
        self,
        include_candidates: bool = False,
        owner_id: str | None = None,
        caller_owner_id: str | None | object = _UNSET,
    ) -> list[Skill]:
        """Load skill files from the directory, defaulting to validated skills only.

        Isolates untrusted candidate skills by default to prevent injection into prompt depth.
        Preserves tenant locality:
        - When caller_owner_id is None, exposes shared system skills only.
        - When caller_owner_id is specified, exposes shared skills plus caller's tenant skills.
        - For backwards-compatible callers, owner_id filters if provided, or returns all.
        """
        skills: list[Skill] = []
        for skill in self._load_raw_all(include_candidates=include_candidates):
            if caller_owner_id is not _UNSET:
                if caller_owner_id is None:
                    # Shared system skills only
                    if skill.owner_id is not None:
                        continue
                elif skill.owner_id is not None and skill.owner_id != caller_owner_id:
                    continue
            elif owner_id is not None and skill.owner_id is not None and skill.owner_id != owner_id:
                continue

            skills.append(skill)
        return skills

    def load_candidates(
        self,
        owner_id: str | None = None,
        caller_owner_id: str | None | object = _UNSET,
    ) -> list[Skill]:
        """Load only untrusted candidate skills awaiting validation, scoped by tenant locality."""
        candidates: list[Skill] = []
        for skill in self._load_raw_all(include_candidates=True):
            if not skill.is_candidate:
                continue
            if caller_owner_id is not _UNSET:
                if caller_owner_id is None:
                    if skill.owner_id is not None:
                        continue
                elif skill.owner_id is not None and skill.owner_id != caller_owner_id:
                    continue
            elif owner_id is not None and skill.owner_id is not None and skill.owner_id != owner_id:
                continue

            candidates.append(skill)
        return candidates

    def get(
        self,
        name: str,
        owner_id: str | None = None,
        caller_owner_id: str | None | object = _UNSET,
    ) -> Skill | None:
        """Find a skill by name or slug, checking ownership scope.

        If the skill belongs to another tenant, returns None to avoid disclosing its existence.
        """
        target_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip().lower())
        for skill in self._load_raw_all(include_candidates=True):
            skill_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", skill.name.strip().lower())
            if skill.name.lower() == name.lower() or skill_slug == target_slug:
                if caller_owner_id is not _UNSET:
                    if caller_owner_id is None:
                        if skill.owner_id is not None:
                            return None
                    elif skill.owner_id is not None and skill.owner_id != caller_owner_id:
                        return None
                elif (
                    owner_id is not None
                    and skill.owner_id is not None
                    and skill.owner_id != owner_id
                ):
                    return None
                return skill
        return None

    def find_by_attempt_id(self, attempt_id: str) -> Skill | None:
        """Find an existing candidate or validated skill matching an execution attempt ID."""
        target = str(attempt_id)
        for skill in self._load_raw_all(include_candidates=True):
            if skill.attempt_id == target:
                return skill
        return None

    def save(self, skill: Skill) -> Path:
        """Write a skill to disk as a Markdown file with YAML frontmatter atomically."""
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", skill.name.strip().lower())
        target_path = self._get_path_for_name(skill.name)
        filename = target_path.name

        lock = self._get_skill_lock(slug)
        with lock:
            if target_path.exists():
                existing = self._parse_file(target_path)
                if existing is not None and existing.name.lower() != skill.name.lower():
                    raise SkillCollisionError(
                        f"Skill name '{skill.name}' collides with existing skill '{existing.name}'"
                    )

            meta_dict: dict[str, Any] = {
                "name": skill.name,
                "description": skill.description,
                "triggers": skill.triggers,
                "required_tools": skill.required_tools,
                "status": skill.status,
            }
            if skill.id:
                meta_dict["id"] = skill.id
            if skill.provenance:
                meta_dict["provenance"] = skill.provenance
            if skill.review_audit:
                meta_dict["review_audit"] = skill.review_audit.model_dump()
            if skill.validation_notes:
                meta_dict["validation_notes"] = skill.validation_notes

            frontmatter = yaml.dump(
                meta_dict,
                default_flow_style=False,
            )

            content = f"---\n{frontmatter}---\n{skill.instructions}"

            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self._dir,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
                encoding="utf-8",
            ) as temp_file:
                temp_path = Path(temp_file.name)
                try:
                    temp_file.write(content)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                except Exception:
                    if temp_path.exists():
                        temp_path.unlink()
                    raise

            os.replace(temp_path, target_path)

        return target_path

    def promote_candidate(
        self,
        name: str,
        validator_identity: str,
        notes: str | None = None,
        owner_id: str | None = None,
        caller_owner_id: str | None | object = _UNSET,
    ) -> Skill:
        """Validate an untrusted candidate skill, promoting it to active execution status.

        Thread-safe and concurrency-safe via per-skill lock.
        Validates state transitions:
        - If rejected: raises InvalidStateTransitionError.
        - If validated: returns existing validated skill idempotently.
        - If candidate: updates status to validated, records ReviewAudit.
        """
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip().lower())
        lock = self._get_skill_lock(slug)
        with lock:
            skill = None
            for s in self._load_raw_all(include_candidates=True):
                s_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", s.name.strip().lower())
                if s.name.lower() == name.lower() or s_slug == slug:
                    skill = s
                    break

            if skill is None:
                raise ValueError(f"Candidate skill '{name}' not found for promotion")

            effective_caller = caller_owner_id if caller_owner_id is not _UNSET else owner_id
            if (
                effective_caller is not None
                and skill.owner_id is not None
                and skill.owner_id != effective_caller
            ):
                raise ValueError(f"Candidate skill '{name}' not found for promotion")

            if skill.is_rejected:
                raise InvalidStateTransitionError(
                    f"Candidate skill '{name}' was rejected and cannot be promoted"
                )

            if skill.is_validated:
                # Idempotent replay: return existing validated skill without mutating review audit
                return skill

            if not skill.is_candidate:
                raise InvalidStateTransitionError(
                    f"Skill '{name}' is not a candidate (current status: {skill.status})"
                )

            skill.status = "validated"
            skill.validation_notes = notes or f"Validated by {validator_identity}"
            skill.review_audit = ReviewAudit(
                decision="promoted",
                operator_id=validator_identity,
                timestamp=datetime.now(UTC).isoformat(),
                notes=notes,
            )
            # Immutability: do not alter skill.provenance
            self.save(skill)
            return skill

    def reject_candidate(
        self,
        name: str,
        reason: str = "",
        operator_id: str = "operator",
        owner_id: str | None = None,
        caller_owner_id: str | None | object = _UNSET,
    ) -> Skill:
        """Reject an untrusted candidate skill, preventing promotion into prompt depth.

        Thread-safe and concurrency-safe via per-skill lock.
        Validates state transitions:
        - If validated: raises InvalidStateTransitionError.
        - If rejected: returns existing rejected skill idempotently.
        - If candidate: updates status to rejected, records ReviewAudit.
        """
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip().lower())
        lock = self._get_skill_lock(slug)
        with lock:
            skill = None
            for s in self._load_raw_all(include_candidates=True):
                s_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", s.name.strip().lower())
                if s.name.lower() == name.lower() or s_slug == slug:
                    skill = s
                    break

            if skill is None:
                raise ValueError(f"Candidate skill '{name}' not found for rejection")

            effective_caller = caller_owner_id if caller_owner_id is not _UNSET else owner_id
            if (
                effective_caller is not None
                and skill.owner_id is not None
                and skill.owner_id != effective_caller
            ):
                raise ValueError(f"Candidate skill '{name}' not found for rejection")

            if skill.is_validated:
                raise InvalidStateTransitionError(
                    f"Validated skill '{name}' cannot be rejected in this version"
                )

            if skill.is_rejected:
                # Idempotent replay: return existing rejected skill without mutating review audit
                return skill

            if not skill.is_candidate:
                raise InvalidStateTransitionError(
                    f"Skill '{name}' is not a candidate (current status: {skill.status})"
                )

            skill.status = "rejected"
            skill.validation_notes = reason
            skill.review_audit = ReviewAudit(
                decision="rejected",
                operator_id=operator_id,
                timestamp=datetime.now(UTC).isoformat(),
                notes=reason,
            )
            # Immutability: do not alter skill.provenance
            self.save(skill)
            return skill

    @staticmethod
    def _parse_file(path: Path) -> Skill | None:
        """Parse a Markdown skill file."""
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return None

        match = _FRONTMATTER_PATTERN.match(raw)
        if not match:
            return None

        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None

        if not isinstance(meta, dict) or "name" not in meta:
            return None

        review_audit = None
        review_audit_raw = meta.get("review_audit")
        if isinstance(review_audit_raw, dict):
            try:
                review_audit = ReviewAudit.model_validate(review_audit_raw)
            except Exception:
                review_audit = None

        return Skill(
            id=meta.get("id"),
            name=meta["name"],
            description=meta.get("description", ""),
            triggers=meta.get("triggers", []),
            required_tools=meta.get("required_tools", []),
            instructions=match.group(2).strip(),
            status=meta.get("status", "validated"),
            provenance=meta.get("provenance"),
            review_audit=review_audit,
            validation_notes=meta.get("validation_notes"),
        )
