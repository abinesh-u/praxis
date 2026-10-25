"""Evidence synthesizer constructing verifiable domain Evidence from raw dispatch facts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from praxis_core.entities.evidence import Evidence
from praxis_core.ports.action_dispatcher import RawDispatchResult
from praxis_core.ports.status_reconciler import RawReconcileResult


class EvidenceSynthesizer:
    """Evaluates raw execution facts against criteria to produce immutable Evidence."""

    @staticmethod
    def verify_and_synthesize_webhook_receipt(
        task_id: UUID,
        action_id: UUID,
        attempt_id: UUID,
        raw_result: RawDispatchResult | RawReconcileResult,
    ) -> Evidence | None:
        """Verify webhook response semantics and construct machine-verified evidence.

        Returns None if the raw facts do not provide authoritative proof of completed execution.
        """
        if raw_result.status != "completed":
            return None

        payload = raw_result.raw_payload
        if not isinstance(payload, dict):
            return None

        provider_status = payload.get("status")
        if provider_status != "completed":
            return None

        operation_id = raw_result.provider_operation_id or payload.get("operation_id")
        if not operation_id:
            return None

        details: dict[str, Any] = {
            "provider_response": payload,
            "operation_id": str(operation_id),
        }
        return Evidence.machine_verified(
            target_task_id=task_id,
            target_action_id=action_id,
            target_run_id=str(attempt_id),
            verifier_identity="integration:webhook_post",
            details=details,
        )

    @staticmethod
    def verify_and_synthesize_local_receipt(
        task_id: UUID,
        action_id: UUID,
        attempt_id: UUID,
        owner_id: str,
        action_description: str,
        raw_result: RawDispatchResult,
    ) -> Evidence | None:
        """Verify local execution facts and construct domain evidence."""
        if raw_result.status != "completed":
            return None

        payload = raw_result.raw_payload
        details: dict[str, Any] = {"raw_output": payload}

        # If payload indicates manual step with attributable user confirmation
        if isinstance(payload, dict) and payload.get("human_confirmed"):
            return Evidence.human_confirmed(
                target_task_id=task_id,
                target_action_id=action_id,
                user_identity=f"cli:{owner_id}",
                confirmation_note=(
                    payload.get("note") or f"Action '{action_description}' confirmed by user."
                ),
            )

        # Standard machine-verified local execution
        return Evidence.machine_verified(
            target_task_id=task_id,
            target_action_id=action_id,
            target_run_id=str(attempt_id),
            verifier_identity=f"cli:{owner_id}",
            details=details,
        )
