"""Tests for skill store, matching, and file persistence."""

from praxis_agent_runtime.skills.matcher import match_skills
from praxis_agent_runtime.skills.models import Skill
from praxis_agent_runtime.skills.skill_store import SkillStore


class TestSkillStore:
    def test_save_and_load(self, tmp_path):
        store = SkillStore(tmp_path)
        skill = Skill(
            name="test_skill",
            description="A test skill",
            triggers=["test", "debug"],
            required_tools=["echo"],
            instructions="## Steps\n1. Do the thing.",
        )
        path = store.save(skill)
        assert path.exists()

        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].name == "test_skill"
        assert loaded[0].triggers == ["test", "debug"]
        assert "Do the thing" in loaded[0].instructions

    def test_load_empty_dir(self, tmp_path):
        store = SkillStore(tmp_path)
        assert store.load_all() == []

    def test_invalid_file_skipped(self, tmp_path):
        (tmp_path / "bad.md").write_text("no frontmatter here")
        store = SkillStore(tmp_path)
        assert store.load_all() == []


class TestSkillMatcher:
    def test_matches_by_trigger_keywords(self):
        skills = [
            Skill(name="git_skill", description="Git ops", triggers=["git", "branch"]),
            Skill(name="file_skill", description="File ops", triggers=["file", "read"]),
        ]
        matches = match_skills("clean up git branches", skills)
        assert len(matches) == 1
        assert matches[0].name == "git_skill"

    def test_no_matches(self):
        skills = [
            Skill(name="unrelated", description="Nothing", triggers=["quantum", "physics"]),
        ]
        matches = match_skills("read a file", skills)
        assert matches == []

    def test_max_results(self):
        skills = [Skill(name=f"s{i}", description="", triggers=["common"]) for i in range(10)]
        matches = match_skills("common task", skills, max_results=3)
        assert len(matches) == 3
