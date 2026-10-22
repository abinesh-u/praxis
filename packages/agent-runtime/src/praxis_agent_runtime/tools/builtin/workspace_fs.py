"""Workspace filesystem tools — scoped to an approved workspace root."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from praxis_agent_runtime.tools.base import BaseTool
from praxis_agent_runtime.types import ActionRiskLevel, ToolResult


def _resolve_safe(workspace_root: str, relative_path: str) -> str:
    """Resolve a path and verify it stays inside the workspace root."""
    root = os.path.realpath(workspace_root)
    target = os.path.realpath(os.path.join(root, relative_path))
    if not target.startswith(root + os.sep) and target != root:
        raise PermissionError(f"Path '{relative_path}' resolves outside workspace root")
    return target


class FsReadFileArgs(BaseModel):
    path: str = Field(description="Relative path within the workspace")
    max_bytes: int = Field(default=100_000, description="Max bytes to read (safety limit)")


class FsReadFileTool(BaseTool):
    name = "fs_read_file"
    description = "Read the contents of a file in the approved workspace."
    risk_level = ActionRiskLevel.READ_ONLY
    args_schema = FsReadFileArgs
    timeout_seconds = 10

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    def execute(self, *, path: str, max_bytes: int = 100_000) -> ToolResult:
        try:
            resolved = _resolve_safe(self._workspace_root, path)
            content = Path(resolved).read_text(encoding="utf-8")[:max_bytes]
            return ToolResult(
                success=True,
                output=content,
                evidence={"path": resolved, "size": len(content)},
            )
        except (PermissionError, FileNotFoundError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))


class FsWriteFileArgs(BaseModel):
    path: str = Field(description="Relative path within the workspace")
    content: str = Field(description="Content to write")


class FsWriteFileTool(BaseTool):
    name = "fs_write_file"
    description = "Write content to a file in the approved workspace. Creates parent dirs."
    risk_level = ActionRiskLevel.CONSEQUENTIAL
    args_schema = FsWriteFileArgs
    timeout_seconds = 10

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    def execute(self, *, path: str, content: str) -> ToolResult:
        try:
            resolved = _resolve_safe(self._workspace_root, path)
            target = Path(resolved)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            actual_size = target.stat().st_size
            return ToolResult(
                success=True,
                output=f"Wrote {actual_size} bytes to {path}",
                evidence={"path": resolved, "size": actual_size},
            )
        except (PermissionError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))


class FsListDirArgs(BaseModel):
    path: str = Field(default=".", description="Relative directory path")
    max_entries: int = Field(default=200, description="Max entries to return")


class FsListDirTool(BaseTool):
    name = "fs_list_dir"
    description = "List files and directories inside the approved workspace."
    risk_level = ActionRiskLevel.READ_ONLY
    args_schema = FsListDirArgs
    timeout_seconds = 10

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    def execute(self, *, path: str = ".", max_entries: int = 200) -> ToolResult:
        try:
            resolved = _resolve_safe(self._workspace_root, path)
            entries = sorted(os.listdir(resolved))[:max_entries]
            return ToolResult(
                success=True,
                output=entries,
                evidence={"path": resolved, "count": len(entries)},
            )
        except (PermissionError, FileNotFoundError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))
