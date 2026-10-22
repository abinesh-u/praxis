"""Domain services for validating dependency graphs and evaluating blocker states."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from praxis_core.entities.common import DependencyType, TaskStatus
from praxis_core.entities.task import Task
from praxis_core.errors import DependencyCycleError


class DependencyGraphValidator:
    """Validates dependency relationships and derives blocker status from prerequisites."""

    @staticmethod
    def check_acyclic(tasks: list[Task]) -> None:
        """Verify that the task dependency graph contains no circular dependencies.

        Raises:
            DependencyCycleError: If any directed cycle (A depends on B depends on A) is found.
        """
        adj: dict[UUID, list[UUID]] = {t.id: [] for t in tasks}
        for task in tasks:
            for dep in task.dependencies:
                if (
                    dep.dependency_type == DependencyType.BLOCKS
                    and dep.depends_on_task_id in adj
                    and dep.depends_on_task_id not in adj[task.id]
                ):
                    adj[task.id].append(dep.depends_on_task_id)

        # 0 = unvisited, 1 = visiting (in current stack), 2 = visited
        visited: dict[UUID, int] = dict.fromkeys(adj, 0)
        parent: dict[UUID, UUID | None] = dict.fromkeys(adj)

        def dfs(node: UUID, path: list[UUID]) -> None:
            visited[node] = 1
            path.append(node)

            for neighbor in adj.get(node, []):
                if visited.get(neighbor) == 1:
                    idx = path.index(neighbor)
                    cycle = path[idx:] + [neighbor]
                    raise DependencyCycleError(cycle)
                elif visited.get(neighbor) == 0:
                    parent[neighbor] = node
                    dfs(neighbor, path)

            path.pop()
            visited[node] = 2

        for task_id in list(adj.keys()):
            if visited[task_id] == 0:
                dfs(task_id, [])

    @staticmethod
    def evaluate_blockers(
        task: Task,
        task_lookup: Callable[[UUID], Task | None],
    ) -> tuple[bool, list[UUID]]:
        """Evaluate whether a task is blocked based on prerequisite task completion states.

        Returns:
            tuple[bool, list[UUID]]: (is_blocked, list of unsatisfied prerequisite task IDs)
        """
        blocking_ids: list[UUID] = []
        for dep in task.dependencies:
            if dep.dependency_type != DependencyType.BLOCKS:
                continue

            prereq = task_lookup(dep.depends_on_task_id)
            if prereq is None or prereq.status != TaskStatus.COMPLETED:
                blocking_ids.append(dep.depends_on_task_id)

        return len(blocking_ids) > 0, blocking_ids
