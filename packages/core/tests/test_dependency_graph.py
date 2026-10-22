"""Unit tests for dependency graphs, cycle detection, and blocker evaluation."""

from uuid import uuid4

import pytest
from praxis_core.domain_services.dependency_graph import DependencyGraphValidator
from praxis_core.entities.common import DependencyType
from praxis_core.entities.dependency import Dependency
from praxis_core.entities.evidence import Evidence
from praxis_core.entities.task import Task
from praxis_core.errors import DependencyCycleError, SelfDependencyError


class TestDependencyInvariants:
    """Verifies self-dependency rejection and cycle prevention."""

    def test_self_dependency_raises_error(self):
        task_id = uuid4()
        with pytest.raises(SelfDependencyError) as exc_info:
            Dependency(task_id=task_id, depends_on_task_id=task_id)
        assert exc_info.value.task_id == task_id

    def test_direct_cycle_detected(self):
        task_a = Task(owner_id="u1", title="Task A")
        task_b = Task(owner_id="u1", title="Task B")

        # A depends on B, and B depends on A
        task_a.add_dependency(task_b.id, DependencyType.BLOCKS)
        task_b.add_dependency(task_a.id, DependencyType.BLOCKS)

        with pytest.raises(DependencyCycleError) as exc_info:
            DependencyGraphValidator.check_acyclic([task_a, task_b])
        assert len(exc_info.value.cycle_path) >= 2

    def test_transitive_cycle_detected(self):
        task_a = Task(owner_id="u1", title="Task A")
        task_b = Task(owner_id="u1", title="Task B")
        task_c = Task(owner_id="u1", title="Task C")

        # A -> B -> C -> A
        task_a.add_dependency(task_b.id, DependencyType.BLOCKS)
        task_b.add_dependency(task_c.id, DependencyType.BLOCKS)
        task_c.add_dependency(task_a.id, DependencyType.BLOCKS)

        with pytest.raises(DependencyCycleError) as exc_info:
            DependencyGraphValidator.check_acyclic([task_a, task_b, task_c])
        assert task_a.id in exc_info.value.cycle_path
        assert task_b.id in exc_info.value.cycle_path
        assert task_c.id in exc_info.value.cycle_path

    def test_valid_dag_passes_acyclic_check(self):
        task_a = Task(owner_id="u1", title="Task A")
        task_b = Task(owner_id="u1", title="Task B")
        task_c = Task(owner_id="u1", title="Task C")

        # C depends on B, B depends on A (A -> B -> C is acyclic)
        task_c.add_dependency(task_b.id, DependencyType.BLOCKS)
        task_b.add_dependency(task_a.id, DependencyType.BLOCKS)

        # Should not raise
        DependencyGraphValidator.check_acyclic([task_a, task_b, task_c])


class TestBlockerEvaluation:
    """Verifies that dependency satisfaction derives strictly from prerequisite terminal state."""

    def test_prerequisite_in_progress_blocks_dependent_task(self):
        prereq = Task(owner_id="u1", title="Prerequisite Task")
        dependent = Task(owner_id="u1", title="Dependent Task")
        dependent.add_dependency(prereq.id, DependencyType.BLOCKS)

        prereq.start()
        tasks = {prereq.id: prereq, dependent.id: dependent}

        is_blocked, blocking_ids = DependencyGraphValidator.evaluate_blockers(
            dependent, lambda tid: tasks.get(tid)
        )
        assert is_blocked is True
        assert prereq.id in blocking_ids

    def test_prerequisite_completed_unblocks_dependent_task(self):
        prereq = Task(owner_id="u1", title="Prerequisite Task")
        dependent = Task(owner_id="u1", title="Dependent Task")
        dependent.add_dependency(prereq.id, DependencyType.BLOCKS)

        prereq.start()
        prereq.complete(
            Evidence.machine_verified(
                target_task_id=prereq.id,
                verifier_identity="tool:done",
                details={},
            )
        )
        tasks = {prereq.id: prereq, dependent.id: dependent}

        is_blocked, blocking_ids = DependencyGraphValidator.evaluate_blockers(
            dependent, lambda tid: tasks.get(tid)
        )
        assert is_blocked is False
        assert len(blocking_ids) == 0

    def test_relation_dependency_does_not_block(self):
        prereq = Task(owner_id="u1", title="Contextual Task")
        dependent = Task(owner_id="u1", title="Dependent Task")
        # Soft relation, not hard BLOCKS
        dependent.add_dependency(prereq.id, DependencyType.RELATION)

        tasks = {prereq.id: prereq, dependent.id: dependent}

        is_blocked, blocking_ids = DependencyGraphValidator.evaluate_blockers(
            dependent, lambda tid: tasks.get(tid)
        )
        assert is_blocked is False
        assert len(blocking_ids) == 0
