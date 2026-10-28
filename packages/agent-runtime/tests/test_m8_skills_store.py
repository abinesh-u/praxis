"""Adversarial and behavioral test suite for M8 hardened SkillStore.

Covers:
1. Safe slug normalization, collision rejection (a b vs a@b), and overwrite prevention.
2. Atomic file persistence and failure isolation (partial write failure preserves original).
3. Concurrency-safe state transitions and thread synchronization.
4. Terminal rejection integrity (rejected candidate cannot be promoted).
5. Immutable execution provenance preservation and separate ReviewAudit recording.
6. Tenant locality isolation and shared vs private skill visibility.
"""

from __future__ import annotations

import concurrent.futures
from unittest.mock import patch

import pytest
from praxis_agent_runtime.skills.models import (
    InvalidStateTransitionError,
    Skill,
    SkillCollisionError,
)
from praxis_agent_runtime.skills.skill_store import SkillStore


class TestM8SkillStoreHardening:
    """Test suite validating M8 security, collision, and state machine invariants."""

    def test_collision_rejection_preserves_existing_skill(self, tmp_path):
        """Distinct skill names mapping to the same slug must be rejected without overwriting."""
        store = SkillStore(tmp_path)
        skill1 = Skill(
            name="deploy pipeline",
            description="First pipeline deployer",
            triggers=["deploy", "pipeline"],
            instructions="Step 1: run deploy",
            status="validated",
        )
        path1 = store.save(skill1)
        assert path1.exists()

        # Skill with distinct name that normalizes to the same slug "deploy_pipeline"
        skill2 = Skill(
            name="deploy@pipeline",
            description="Second malicious or colliding pipeline deployer",
            triggers=["deploy"],
            instructions="Step 1: malicious override",
            status="candidate",
        )

        with pytest.raises(SkillCollisionError) as exc_info:
            store.save(skill2)
        assert "collides with existing skill" in str(exc_info.value)

        # Invariant: existing skill file is preserved intact
        preserved = store.get("deploy pipeline")
        assert preserved is not None
        assert preserved.name == "deploy pipeline"
        assert preserved.description == "First pipeline deployer"
        assert preserved.instructions == "Step 1: run deploy"

    def test_path_traversal_rejection(self, tmp_path):
        """Skill names attempting directory traversal must fail closed."""
        store = SkillStore(tmp_path)
        malicious = Skill(
            name="../../etc/passwd",
            description="traversal attempt",
            instructions="exploit",
        )
        # re.sub turns / into _ so slug is ______etc_passwd which is inside tmp_path
        # But if raw name or path resolution attempts escape, it must be caught
        path = store.save(malicious)
        assert path.resolve().is_relative_to(tmp_path.resolve())

    def test_atomic_file_write_failure_preserves_original(self, tmp_path):
        """A failure partway through file write must leave the existing skill intact."""
        store = SkillStore(tmp_path)
        original = Skill(
            name="safe_skill",
            description="Original description",
            instructions="Original instructions",
            status="validated",
        )
        store.save(original)

        # Mock os.replace to simulate sudden failure (disk full, permission, crash)
        updated = original.model_copy(update={"description": "Tampered description"})
        with patch("os.replace", side_effect=OSError("Disk write failed")), pytest.raises(OSError):
            store.save(updated)

        # Invariant: original skill remains completely intact
        loaded = store.get("safe_skill")
        assert loaded is not None
        assert loaded.description == "Original description"

    def test_concurrency_safe_state_transitions(self, tmp_path):
        """Concurrent requests to promote or reject the same candidate serialize cleanly."""
        store = SkillStore(tmp_path)
        candidate = Skill(
            name="concurrent_target",
            description="Candidate under concurrent review",
            status="candidate",
            instructions="Do steps",
            provenance={"attempt_id": "att_123", "owner_id": "tenant_1"},
        )
        store.save(candidate)

        results = []

        def do_promote():
            try:
                store.promote_candidate(
                    "concurrent_target", validator_identity="op_1", notes="Promoted"
                )
                return "promoted"
            except Exception as e:
                return type(e).__name__

        def do_reject():
            try:
                store.reject_candidate("concurrent_target", reason="Rejected", operator_id="op_2")
                return "rejected"
            except Exception as e:
                return type(e).__name__

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(do_promote)
            fut2 = executor.submit(do_reject)
            results = [fut1.result(), fut2.result()]

        # Exactly one must transition state; the second must raise InvalidStateTransitionError
        assert ("promoted" in results and "InvalidStateTransitionError" in results) or (
            "rejected" in results and "InvalidStateTransitionError" in results
        )

        final_skill = store.get("concurrent_target", caller_owner_id="tenant_1")
        assert final_skill is not None
        assert final_skill.status in ("validated", "rejected")

    def test_rejected_candidate_cannot_be_promoted(self, tmp_path):
        """A candidate that was rejected is in terminal state and cannot be promoted."""
        store = SkillStore(tmp_path)
        candidate = Skill(
            name="rejected_candidate",
            description="Flawed procedure",
            status="candidate",
            instructions="Flawed instructions",
            provenance={"attempt_id": "att_999", "owner_id": "tenant_a"},
        )
        store.save(candidate)

        rejected = store.reject_candidate(
            "rejected_candidate", reason="Security risk detected", operator_id="security_officer"
        )
        assert rejected.status == "rejected"
        assert rejected.is_rejected is True

        # Attempt to promote a terminal rejected skill must fail
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            store.promote_candidate("rejected_candidate", validator_identity="rogue_op")
        assert "was rejected and cannot be promoted" in str(exc_info.value)

    def test_repeated_promotion_and_rejection_are_idempotent(self, tmp_path):
        """Repeated promotion or rejection calls must be deterministic without duplicate audits."""
        store = SkillStore(tmp_path)
        candidate = Skill(
            name="idempotent_test",
            description="Test skill",
            status="candidate",
            instructions="Steps",
        )
        store.save(candidate)

        # First promotion
        first_promoted = store.promote_candidate(
            "idempotent_test", validator_identity="op_a", notes="Note 1"
        )
        audit_1 = first_promoted.review_audit
        assert audit_1 is not None
        assert audit_1.decision == "promoted"
        assert audit_1.operator_id == "op_a"

        # Second promotion (idempotent replay)
        second_promoted = store.promote_candidate(
            "idempotent_test", validator_identity="op_b", notes="Note 2"
        )
        assert second_promoted.status == "validated"
        assert second_promoted.review_audit.operator_id == "op_a"
        assert second_promoted.review_audit.timestamp == audit_1.timestamp

    def test_provenance_immutability_and_review_audit_separation(self, tmp_path):
        """Source execution provenance must remain strictly immutable during promotion."""
        store = SkillStore(tmp_path)
        source_prov = {
            "attempt_id": "attempt_xyz",
            "task_id": "task_abc",
            "owner_id": "tenant_prod",
            "evidence_id": "ev_123",
            "evidence_hash": "hash_sec_456",
        }
        candidate = Skill(
            name="provenance_audit_test",
            description="Distilled procedural task",
            status="candidate",
            instructions="Execute verified steps",
            provenance=dict(source_prov),
        )
        store.save(candidate)

        promoted = store.promote_candidate(
            "provenance_audit_test",
            validator_identity="lead_auditor",
            notes="Compliance approved",
        )

        # Source provenance must be identical to original evidence
        assert promoted.provenance == source_prov

        # Review audit is stored separately
        assert promoted.review_audit is not None
        assert promoted.review_audit.decision == "promoted"
        assert promoted.review_audit.operator_id == "lead_auditor"
        assert promoted.review_audit.notes == "Compliance approved"

    def test_shared_vs_tenant_owned_skill_visibility(self, tmp_path):
        """Lookup rules:

        - caller_owner_id=None -> shared system skills only.
        - caller_owner_id=Tenant A -> shared + Tenant A skills.
        - caller_owner_id=Tenant B -> shared + Tenant B skills (Tenant A skill not disclosed).
        """
        store = SkillStore(tmp_path)

        # 1. Shared system skill (owner_id is None)
        shared = Skill(
            name="shared_skill",
            description="System shared skill",
            status="validated",
            provenance=None,
        )
        store.save(shared)

        # 2. Tenant A private skill
        tenant_a_skill = Skill(
            name="tenant_a_private",
            description="Tenant A private skill",
            status="validated",
            provenance={"owner_id": "tenant_a"},
        )
        store.save(tenant_a_skill)

        # 3. Tenant B private skill
        tenant_b_skill = Skill(
            name="tenant_b_private",
            description="Tenant B private skill",
            status="validated",
            provenance={"owner_id": "tenant_b"},
        )
        store.save(tenant_b_skill)

        # Test caller_owner_id=None: shared only
        unauth_skills = store.load_all(caller_owner_id=None)
        unauth_names = [s.name for s in unauth_skills]
        assert "shared_skill" in unauth_names
        assert "tenant_a_private" not in unauth_names
        assert "tenant_b_private" not in unauth_names

        # Test caller_owner_id="tenant_a"
        tenant_a_skills = store.load_all(caller_owner_id="tenant_a")
        a_names = [s.name for s in tenant_a_skills]
        assert "shared_skill" in a_names
        assert "tenant_a_private" in a_names
        assert "tenant_b_private" not in a_names

        # Test caller_owner_id="tenant_b"
        tenant_b_skills = store.load_all(caller_owner_id="tenant_b")
        b_names = [s.name for s in tenant_b_skills]
        assert "shared_skill" in b_names
        assert "tenant_b_private" in b_names
        assert "tenant_a_private" not in b_names

        # Direct get test: Tenant B requests Tenant A's skill -> returns None (no disclosure)
        assert store.get("tenant_a_private", caller_owner_id="tenant_b") is None
        assert store.get("tenant_a_private", caller_owner_id="tenant_a") is not None
