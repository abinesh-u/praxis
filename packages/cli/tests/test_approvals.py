"""Integration tests for praxis approvals."""

import asyncio
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, ApprovalStatus, TaskStatus
from praxis_core.entities.task import Task
from typer.testing import CliRunner

runner = CliRunner()


def test_approvals_list_and_approve(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Clean Disk", status=TaskStatus.AWAITING_APPROVAL)
    action_spec = ActionSpecification(tool_name="docker_system_prune", task_id=task.id)
    approval, _ = ApprovalRequest.create(
        owner_id="custom",
        task_id=task.id,
        action=action_spec,
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="Clean up unused images",
    )

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.approvals.save(approval)
            await uow.commit()

    asyncio.run(_seed())

    appr_short = str(approval.id).replace("-", "")[:8]

    # Test list
    res_list = runner.invoke(app, ["approvals", "list"])
    assert res_list.exit_code == 0
    assert appr_short in res_list.stdout
    assert "docker_system" in res_list.stdout

    # Test approve
    res_appr = runner.invoke(app, ["approvals", "approve", appr_short])
    assert res_appr.exit_code == 0
    assert "Approval granted" in res_appr.stdout

    # Verify task unblocked to IN_PROGRESS
    async def _check():
        async with uow:
            t = await uow.tasks.get_for_owner(task.id, "custom")
            assert t.status == TaskStatus.IN_PROGRESS
            a = await uow.approvals.get_for_owner(approval.id, "custom")
            assert a.status == ApprovalStatus.APPROVED

    asyncio.run(_check())


def test_approvals_reject(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Drop DB", status=TaskStatus.AWAITING_APPROVAL)
    action_spec = ActionSpecification(tool_name="drop_database", task_id=task.id)
    approval, _ = ApprovalRequest.create(
        owner_id="custom",
        task_id=task.id,
        action=action_spec,
        risk_level=ActionRiskLevel.DESTRUCTIVE,
        justification="Reset database",
    )

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.approvals.save(approval)
            await uow.commit()

    asyncio.run(_seed())

    appr_short = str(approval.id).replace("-", "")[:8]
    res = runner.invoke(app, ["approvals", "reject", appr_short, "--reason", "Too dangerous"])
    assert res.exit_code == 0
    assert "Action rejected" in res.stdout

    async def _check():
        async with uow:
            a = await uow.approvals.get_for_owner(approval.id, "custom")
            assert a.status == ApprovalStatus.REJECTED

    asyncio.run(_check())
