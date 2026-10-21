"""Tests for the slow learning loop."""

from praxis_agent_runtime.learning.learning_loop import evaluate_run, run_learning_loop
from praxis_agent_runtime.skills.skill_store import SkillStore
from praxis_agent_runtime.types import ExecutionStatus, RunRecord, StepRecord, ToolResult


def _make_successful_run(num_tool_calls: int = 3) -> RunRecord:
    """Helper: create a run with N successful tool call/result pairs."""
    run = RunRecord(
        goal="audit the git repository and list files",
        status=ExecutionStatus.COMPLETED,
    )
    step_idx = 0

    for i in range(num_tool_calls):
        run.add_step(
            StepRecord(
                step_index=step_idx,
                step_type="tool_call",
                tool_name=f"tool_{i}",
                tool_args={"arg": f"val_{i}"},
            )
        )
        step_idx += 1

        run.add_step(
            StepRecord(
                step_index=step_idx,
                step_type="tool_result",
                tool_name=f"tool_{i}",
                tool_result=ToolResult(success=True, output=f"result_{i}"),
            )
        )
        step_idx += 1

    return run


class TestEvaluateRun:
    def test_successful_multi_step_produces_skill(self):
        run = _make_successful_run(num_tool_calls=4)
        skill = evaluate_run(run)
        assert skill is not None
        assert "audit" in skill.triggers or "repository" in skill.triggers
        assert len(skill.required_tools) > 0

    def test_too_few_tools_returns_none(self):
        run = _make_successful_run(num_tool_calls=1)
        skill = evaluate_run(run)
        assert skill is None

    def test_failed_run_returns_none(self):
        run = RunRecord(goal="something", status=ExecutionStatus.FAILED)
        skill = evaluate_run(run)
        assert skill is None


class TestRunLearningLoop:
    def test_saves_skill_to_store(self, tmp_path):
        run = _make_successful_run(num_tool_calls=4)
        store = SkillStore(tmp_path)
        skill = run_learning_loop(run, store)
        assert skill is not None
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].name == skill.name
