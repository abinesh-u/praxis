"""Dependency entity linking prerequisite tasks to dependent tasks."""

from __future__ import annotations

import uuid
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from praxis_core.entities.common import DependencyType
from praxis_core.errors import SelfDependencyError


class Dependency(BaseModel):
    """Represents a relationship between a dependent task and its prerequisite.

    Satisfaction semantics are derived from the prerequisite task's terminal state
    (e.g., prerequisite task status is COMPLETED), rather than a stale duplicate boolean.
    """

    id: UUID = Field(default_factory=uuid.uuid4)
    task_id: UUID
    depends_on_task_id: UUID
    dependency_type: DependencyType = DependencyType.BLOCKS

    @model_validator(mode="after")
    def check_not_self_dependent(self) -> Dependency:
        if self.task_id == self.depends_on_task_id:
            raise SelfDependencyError(self.task_id)
        return self
