"""Base tool abstraction."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from praxis_agent_runtime.types import ActionRiskLevel, ToolResult


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    name: str
    description: str
    risk_level: ActionRiskLevel = ActionRiskLevel.READ_ONLY
    args_schema: type[BaseModel] | None = None
    timeout_seconds: int = 30

    @property
    def requires_approval(self) -> bool:
        """Tools with CONSEQUENTIAL or DESTRUCTIVE risk always require approval."""
        return self.risk_level in (
            ActionRiskLevel.CONSEQUENTIAL,
            ActionRiskLevel.DESTRUCTIVE,
        )

    def validate_args(self, arguments: dict[str, Any]) -> BaseModel | None:
        """Validate tool arguments against the declared Pydantic schema."""
        if self.args_schema is None:
            return None
        return self.args_schema.model_validate(arguments)

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with validated arguments."""
        ...

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """Full execution pipeline: validate -> execute -> return result."""
        start = time.monotonic()
        try:
            validated = self.validate_args(arguments)
            kwargs = validated.model_dump() if validated else arguments

            result = self.execute(**kwargs)

            elapsed = int((time.monotonic() - start) * 1000)
            result.duration_ms = elapsed
            return result

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=elapsed,
            )
