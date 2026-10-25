"""Execution risk evaluation policy enforcing fail-closed authorization checks."""

from __future__ import annotations

from dataclasses import dataclass

from praxis_core.entities.common import ActionRiskLevel
from praxis_core.entities.next_action import NextAction

CONSEQUENTIAL_KEYWORDS = frozenset(
    {
        "delete",
        "remove",
        "rm",
        "drop",
        "prune",
        "deploy",
        "publish",
        "destroy",
        "wipe",
        "kill",
    }
)


@dataclass(frozen=True)
class ActionRiskAssessment:
    """Typed policy outcome governing execution authorization."""

    requires_approval: bool
    risk_level: ActionRiskLevel
    permission_scope: str
    justification: str


class ActionRiskPolicy:
    """Pure domain policy evaluating execution risk and authorization requirements."""

    @staticmethod
    def assess(action: NextAction) -> ActionRiskAssessment:
        """Assess the risk profile of an action, failing closed if ambiguous."""
        if action is None:
            return ActionRiskAssessment(
                requires_approval=True,
                risk_level=ActionRiskLevel.CONSEQUENTIAL,
                permission_scope="default",
                justification="Missing action specification requires authorization (fail-closed).",
            )

        # Precedence 1: Explicit aggregate designation
        if action.risk_level in (ActionRiskLevel.CONSEQUENTIAL, ActionRiskLevel.DESTRUCTIVE):
            return ActionRiskAssessment(
                requires_approval=True,
                risk_level=action.risk_level,
                permission_scope="local_exec",
                justification=(
                    f"Action '{action.description}' is explicitly designated as consequential."
                ),
            )

        # Precedence 2: Tool-specific restrictions
        tool_hint = (action.tool_hint or "").strip().lower()
        if tool_hint == "webhook_post":
            return ActionRiskAssessment(
                requires_approval=True,
                risk_level=ActionRiskLevel.CONSEQUENTIAL,
                permission_scope="external_http",
                justification="External webhook dispatch requires authorization.",
            )

        # Precedence 3: Argument and description keyword scanning
        desc_lower = (action.description or "").lower()
        args_str = str(action.tool_args_hint or "").lower()
        if any(kw in desc_lower for kw in CONSEQUENTIAL_KEYWORDS) or any(
            kw in args_str for kw in CONSEQUENTIAL_KEYWORDS
        ):
            return ActionRiskAssessment(
                requires_approval=True,
                risk_level=ActionRiskLevel.CONSEQUENTIAL,
                permission_scope="local_exec",
                justification=f"Action '{action.description}' contains consequential keywords.",
            )

        # Safe routine action
        return ActionRiskAssessment(
            requires_approval=False,
            risk_level=ActionRiskLevel.LOW_RISK,
            permission_scope="local_exec",
            justification=f"Action '{action.description}' is a routine operation.",
        )
