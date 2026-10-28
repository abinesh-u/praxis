"""Routing execution adapter coordinating dispatches across the action seam.

This module provides a routing dispatcher adapter that leverages explicit
action metadata or validated tool types to select the appropriate transport adapter,
preserving architectural depth and locality without guessing from natural language text.
"""

from __future__ import annotations

from uuid import UUID

from praxis_core.ports.action_dispatcher import (
    ActionDispatcher,
    DispatchSpec,
    RawDispatchResult,
)
from praxis_core.ports.status_reconciler import (
    RawReconcileResult,
    StatusReconciler,
)


class RoutingActionDispatcher(ActionDispatcher, StatusReconciler):
    """Routing adapter directing execution specs to registered transport adapters.

    Preserves seam separation by selecting the dispatch strategy from explicit
    action metadata or a validated tool name, never guessing from free text.
    """

    def __init__(
        self,
        default_dispatcher: ActionDispatcher | None = None,
        default_reconciler: StatusReconciler | None = None,
    ) -> None:
        self._dispatchers: dict[str, ActionDispatcher] = {}
        self._reconcilers: dict[str, StatusReconciler] = {}
        self._default_dispatcher = default_dispatcher
        self._default_reconciler = default_reconciler

    def register_dispatcher(
        self,
        strategy_or_tool: str,
        dispatcher: ActionDispatcher,
        reconciler: StatusReconciler | None = None,
    ) -> None:
        """Register a dispatcher adapter and optional reconciler interface for a strategy key."""
        self._dispatchers[strategy_or_tool] = dispatcher
        if reconciler is not None:
            self._reconcilers[strategy_or_tool] = reconciler
        elif isinstance(dispatcher, StatusReconciler):
            self._reconcilers[strategy_or_tool] = dispatcher

    def _resolve_strategy(self, spec: DispatchSpec) -> str | None:
        """Extract explicit dispatch strategy from action metadata or validated tool name."""
        return (
            spec.canonical_args.get("dispatch_strategy")
            or spec.destination_context.get("dispatch_strategy")
            or spec.tool_name
        )

    async def dispatch(self, spec: DispatchSpec) -> RawDispatchResult:
        """Dispatch action specification through matching adapter interface."""
        strategy = self._resolve_strategy(spec)
        target = self._dispatchers.get(strategy) if strategy else None
        if target is None and self._default_dispatcher is not None:
            target = self._default_dispatcher

        if target is None:
            return RawDispatchResult(
                status="failed",
                error=f"No dispatcher adapter registered for strategy '{strategy}'",
                failure_final=True,
            )

        return await target.dispatch(spec)

    async def inspect_status(
        self,
        attempt_id: UUID,
        idempotency_key: str,
        provider_operation_id: str | None,
    ) -> RawReconcileResult:
        """Reconcile execution status across registered status reconcilers."""
        if self._default_reconciler is not None:
            res = await self._default_reconciler.inspect_status(
                attempt_id, idempotency_key, provider_operation_id
            )
            if res.status != "outcome_unknown" or not self._reconcilers:
                return res

        for reconciler in self._reconcilers.values():
            if reconciler is not self._default_reconciler:
                res = await reconciler.inspect_status(
                    attempt_id, idempotency_key, provider_operation_id
                )
                if res.status in ("completed", "failed"):
                    return res

        return RawReconcileResult(
            status="outcome_unknown",
            provider_operation_id=provider_operation_id,
            error="Unable to reconcile attempt across registered reconciler adapters",
        )
