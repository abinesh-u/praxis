"""Shell runner — executes allowlisted commands only, with timeouts."""

from __future__ import annotations

import shlex
import subprocess

from pydantic import BaseModel, Field

from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.types import ActionRiskLevel, ToolResult

ALLOWED_COMMANDS: set[str] = {
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "find",
    "grep",
    "git",
    "python",
    "python3",
    "uv",
    "node",
    "npm",
    "echo",
    "date",
    "pwd",
    "env",
}


class ShellRunArgs(BaseModel):
    command: str = Field(description="The shell command to execute")
    timeout: int = Field(default=30, description="Timeout in seconds")


class ShellRunnerTool(BaseTool):
    name = "shell_run"
    description = (
        "Execute an allowlisted shell command in the workspace. "
        "Only safe, common developer commands are permitted."
    )
    risk_level = ActionRiskLevel.CONSEQUENTIAL
    args_schema = ShellRunArgs
    timeout_seconds = 60

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    def execute(self, *, command: str, timeout: int = 30) -> ToolResult:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return ToolResult(success=False, error=f"Invalid command syntax: {exc}")

        if not parts:
            return ToolResult(success=False, error="Empty command")

        base_cmd = parts[0].split("/")[-1]
        if base_cmd not in ALLOWED_COMMANDS:
            return ToolResult(
                success=False,
                error=f"Command '{base_cmd}' is not in the allowlist: {sorted(ALLOWED_COMMANDS)}",
            )

        try:
            proc = subprocess.run(
                parts,
                cwd=self._workspace_root,
                capture_output=True,
                text=True,
                timeout=min(timeout, self.timeout_seconds),
            )
            output = proc.stdout
            if proc.stderr:
                output += f"\n[stderr]: {proc.stderr}"

            return ToolResult(
                success=proc.returncode == 0,
                output=output.strip()[:50_000],
                evidence={"returncode": proc.returncode, "command": command},
                error=f"Exit code {proc.returncode}" if proc.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))
